import asyncio
import logging
import os
import shutil
import tempfile
import time

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from config import Config
from database import UserSettings
from rename_engine import build_filename
from archive_feature import is_archive_waiting, register_archive_handlers
from settings_panel import register_settings_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("zura")
os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)

app = Client("zura_rename", api_id=Config.API_ID, api_hash=Config.API_HASH,
             bot_token=Config.BOT_TOKEN, parse_mode=ParseMode.DISABLED,
             workers=Config.WORKERS,
             max_concurrent_transmissions=Config.MAX_CONCURRENT_TRANSMISSIONS)
settings = UserSettings(Config.DB_URL, Config.DB_NAME)
MEDIA_FILTER = filters.document | filters.video | filters.audio | filters.animation
ACTIVE = {}
MERGE_SESSIONS = {}

def human(size):
    size = float(size or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024

def progress_text(label, current, total, started):
    elapsed = max(time.monotonic() - started, 0.1)
    percent = min(100.0, current * 100 / total) if total else 0.0
    filled = min(10, int(percent // 10))
    speed = current / elapsed
    eta = int(max(0, total - current) / speed) if speed > 0 and total else 0
    eta_h, eta_rem = divmod(eta, 3600)
    eta_m, eta_s = divmod(eta_rem, 60)
    elapsed_i = int(elapsed)
    elapsed_h, elapsed_rem = divmod(elapsed_i, 3600)
    elapsed_m, elapsed_s = divmod(elapsed_rem, 60)
    stage = "📥 Downloading" if "Download" in label else "📤 Uploading"
    bar = "▰" * filled + "▱" * (10 - filled)
    return (
        f"Progress: [{bar}] {percent:.1f}%\n"
        f"{stage}: {human(current)} | {human(total)}\n"
        f"⚡️ Speed: {human(speed)}/s\n"
        f"⌛ ETA: {eta_h}h {eta_m}m {eta_s}s\n"
        f"⏱️ Time elapsed: {elapsed_h}h {elapsed_m}m {elapsed_s}s"
    )

async def update_progress(status, label, current, total, started, last):
    now = time.monotonic()
    if current < total and now - last[0] < 1.5:
        return
    last[0] = now
    try:
        await status.edit_text(progress_text(label, current, total, started))
    except Exception as exc:
        log.warning("Could not update %s progress message: %s", label, exc)

@app.on_message(filters.private & filters.command(["start", "help"]))
async def start_handler(client, message):
    await settings.ensure_user(message.from_user.id)
    await message.reply_text(
        "ZuraRename Bot\n\n"
        "Set your filename format with /autorenname <format>.\n"
        "Then send a document, video, audio, or animation.\n\n"
        "Placeholders: {filename}, {ext}, {user_id}, {date}, {time}\n"
        "Commands:\n/myformat — show format\n/resetformat — reset format\n"
        "/metadata Subtitle | Audio | Author — set media metadata\n"
        "/mymetadata — show metadata\n/delmetadata — clear metadata\n"
        "/setcaption text — set output caption\n/delcaption — remove custom caption\n"
        "/setthumb — reply to a photo with this command\n/delthumb — remove thumbnail\n"
        "/set_prefix text — add prefix to renamed filenames\n/my_prefix — show prefix\n/del_prefix — remove prefix\n"
        "/merge — start merging video parts\n/done — merge and upload\n/cancel — cancel job or merge mode"
    )

@app.on_message(filters.private & filters.command(["autorenname", "autorename"]))
async def set_format_handler(client, message):
    if len(message.command) < 2:
        current = await settings.get_value(message.from_user.id, "rename_template")
        return await message.reply_text("Usage: /autorenname {filename}_{date}.{ext}" +
                                        (f"\nCurrent: {current}" if current else ""))
    template = message.text.split(maxsplit=1)[1].strip()
    try:
        build_filename(template, "example.mkv", message.from_user.id)
        await settings.set_value(message.from_user.id, "rename_template", template)
    except ValueError as exc:
        return await message.reply_text(f"Invalid format: {exc}")
    await message.reply_text(f"Rename format saved:\n{template}")

@app.on_message(filters.private & filters.command("myformat"))
async def my_format_handler(client, message):
    template = await settings.get_value(message.from_user.id, "rename_template")
    await message.reply_text(f"Current format: {template}" if template else "No format set. Use /autorenname first.")

@app.on_message(filters.private & filters.command("resetformat"))
async def reset_format_handler(client, message):
    await settings.set_value(message.from_user.id, "rename_template", None)
    await message.reply_text("Rename format reset.")

@app.on_message(filters.private & filters.command("metadata"))
async def metadata_toggle_handler(client, message):
    raw = message.text.split(maxsplit=1)[1].strip().lower() if len(message.command) > 1 else ""
    current = await settings.get_value(message.from_user.id, "meta_enabled", False)
    if raw in ("on", "enable", "1"):
        enabled = True
    elif raw in ("off", "disable", "0"):
        enabled = False
    elif not raw:
        enabled = not current
    else:
        return await message.reply_text("Use /metadata to toggle, or /metadata on /metadata off.")
    await settings.set_value(message.from_user.id, "meta_enabled", enabled)
    await message.reply_text("Metadata: ON" if enabled else "Metadata: OFF")

async def save_metadata_field(message, key, label):
    value = message.text.split(maxsplit=1)[1].strip() if len(message.command) > 1 else ""
    if not value:
        return await message.reply_text(f"Usage: /{message.command[0]} Your {label} Here")
    await settings.set_value(message.from_user.id, key, value)
    await message.reply_text(f"{label} metadata saved: {value}")

@app.on_message(filters.private & filters.command("settitle"))
async def set_title_handler(client, message):
    await save_metadata_field(message, "meta_title", "Title")

@app.on_message(filters.private & filters.command("setauthor"))
async def set_author_handler(client, message):
    await save_metadata_field(message, "meta_author", "Author")

@app.on_message(filters.private & filters.command("setartist"))
async def set_artist_handler(client, message):
    await save_metadata_field(message, "meta_artist", "Artist")

@app.on_message(filters.private & filters.command("setaudio"))
async def set_audio_handler(client, message):
    await save_metadata_field(message, "meta_audio", "Audio")

@app.on_message(filters.private & filters.command("setsubtitle"))
async def set_subtitle_handler(client, message):
    await save_metadata_field(message, "meta_subtitle", "Subtitle")

@app.on_message(filters.private & filters.command("setvideo"))
async def set_video_handler(client, message):
    await save_metadata_field(message, "meta_video", "Video")

@app.on_message(filters.private & filters.command("mymetadata"))
async def my_metadata_handler(client, message):
    uid = message.from_user.id
    fields = (("Title", "meta_title"), ("Author", "meta_author"), ("Artist", "meta_artist"),
              ("Audio", "meta_audio"), ("Subtitle", "meta_subtitle"), ("Video", "meta_video"))
    values = [f"{label}: {await settings.get_value(uid, key) or 'Not set'}" for label, key in fields]
    enabled = await settings.get_value(uid, "meta_enabled", False)
    await message.reply_text("Metadata: " + ("ON" if enabled else "OFF") + "\\n" + "\\n".join(values))

@app.on_message(filters.private & filters.command("delmetadata"))
async def delete_metadata_handler(client, message):
    for key in ("meta_title", "meta_author", "meta_artist", "meta_audio", "meta_subtitle", "meta_video"):
        await settings.set_value(message.from_user.id, key, None)
    await message.reply_text("All custom metadata fields cleared. Metadata toggle was not changed.")

@app.on_message(filters.private & filters.command("setcaption"))
async def set_caption_handler(client, message):
    caption = message.text.split(maxsplit=1)[1].strip() if len(message.command) > 1 else ""
    await settings.set_value(message.from_user.id, "caption", caption or None)
    await message.reply_text("Custom caption saved." if caption else "Custom caption removed.")

@app.on_message(filters.private & filters.command("delcaption"))
async def delete_caption_handler(client, message):
    await settings.set_value(message.from_user.id, "caption", None)
    await message.reply_text("Custom caption removed.")

@app.on_message(filters.private & filters.command("setthumb"))
async def set_thumb_handler(client, message):
    reply = message.reply_to_message
    if not reply or not reply.photo:
        return await message.reply_text("Reply to a photo with /setthumb.")
    await settings.set_value(message.from_user.id, "thumb_file_id", reply.photo.file_id)
    await message.reply_text("Custom thumbnail saved.")

@app.on_message(filters.private & filters.command("delthumb"))
async def delete_thumb_handler(client, message):
    await settings.set_value(message.from_user.id, "thumb_file_id", None)
    await message.reply_text("Custom thumbnail removed.")

@app.on_message(filters.private & filters.command("set_prefix"))
async def set_prefix_handler(client, message):
    prefix = message.text.split(maxsplit=1)[1].strip() if len(message.command) > 1 else ""
    if not prefix:
        return await message.reply_text("Usage: /set_prefix text\\nExample: /set_prefix @ZuraFlix")
    await settings.set_value(message.from_user.id, "filename_prefix", prefix)
    await message.reply_text(f"Filename prefix saved: {prefix}")

@app.on_message(filters.private & filters.command("my_prefix"))
async def my_prefix_handler(client, message):
    prefix = await settings.get_value(message.from_user.id, "filename_prefix", "")
    await message.reply_text(f"Current prefix: {prefix or 'None'}")

@app.on_message(filters.private & filters.command("del_prefix"))
async def del_prefix_handler(client, message):
    await settings.set_value(message.from_user.id, "filename_prefix", "")
    await message.reply_text("Filename prefix removed.")

@app.on_message(filters.private & filters.command("cancel"))
async def cancel_handler(client, message):
    uid = message.from_user.id
    if uid in PENDING_RENAMES:
        PENDING_RENAMES.pop(uid, None)
        return await message.reply_text("Rename request cancelled.")
    if uid in MERGE_SESSIONS and uid not in ACTIVE:
        MERGE_SESSIONS.pop(uid, None)
        return await message.reply_text("Merge mode cancelled.")
    task = ACTIVE.get(uid)
    if task and not task.done():
        task.cancel()
        await message.reply_text("Cancellation requested.")
    else:
        await message.reply_text("No active job.")


@app.on_message(filters.private & filters.command("merge"))
async def merge_start_handler(client, message):
    uid = message.from_user.id
    if uid in ACTIVE and not ACTIVE[uid].done():
        return await message.reply_text("Another task is running. Use /cancel first.")
    MERGE_SESSIONS[uid] = []
    await message.reply_text("Merge mode ON. Send video parts one by one in the required order.\nWhen finished, send /done. Use /cancel to stop.\nVideos must have compatible streams/codecs.")

@app.on_message(filters.private & filters.command("done"))
async def merge_done_handler(client, message):
    uid = message.from_user.id
    items = MERGE_SESSIONS.get(uid)
    if items is None:
        return await message.reply_text("Pehle /merge bhejo.")
    if len(items) < 2:
        return await message.reply_text("Merge ke liye kam se kam 2 video files bhejo.")
    ACTIVE[uid] = asyncio.current_task()
    work_dir = tempfile.mkdtemp(prefix="zura_merge_", dir=Config.DOWNLOAD_DIR)
    status = await message.reply_text(f"Preparing {len(items)} files for merge…")
    started, last = time.monotonic(), [0.0]
    try:
        from merge import merge_videos
        local_files = []
        for index, source_message in enumerate(items, 1):
            path = await client.download_media(
                source_message, file_name=os.path.join(work_dir, f"part_{index:03d}.bin"),
                progress=lambda current, total: update_progress(status, f"Downloading part {index}/{len(items)}", current, total, started, last)
            )
            if not path or not os.path.isfile(path):
                raise RuntimeError(f"Could not download part {index}")
            local_files.append(path)
        first_media = items[0].video or items[0].document
        original_name = getattr(first_media, "file_name", None) or "merged_video.mkv"
        stem, ext = os.path.splitext(original_name)
        ext = ext or ".mkv"
        template = await settings.get_value(uid, "rename_template") or "{filename}.{ext}"
        output_name = build_filename(template, f"{stem}_merged{ext}", uid)
        prefix = await settings.get_value(uid, "filename_prefix", "")\n        if prefix and not output_name.startswith(prefix):\n            output_name = prefix + output_name\n        output_path = os.path.join(work_dir, output_name)
        await status.edit_text("Merging video parts…")
        await merge_videos(local_files, output_path)
        caption = await settings.get_value(uid, "caption")
        if caption:
            caption = caption.format(filename=os.path.splitext(output_name)[0], ext=os.path.splitext(output_name)[1].lstrip("."), user_id=uid)
        started, last = time.monotonic(), [0.0]
        await status.edit_text("Uploading merged video…")
        await client.send_video(
            chat_id=message.chat.id, video=output_path, caption=caption or None,
            supports_streaming=True, reply_to_message_id=message.id,
            progress=lambda current, total: update_progress(status, "Uploading merged video", current, total, started, last)
        )
        await status.delete()
    except asyncio.CancelledError:
        try: await status.edit_text("Merge cancelled.")
        except Exception: pass
        raise
    except Exception as exc:
        log.exception("Merge failed for user %s", uid)
        try: await status.edit_text(f"Merge failed: {str(exc)[:650]}\nCheck that all parts have compatible codecs and streams.")
        except Exception: pass
    finally:
        MERGE_SESSIONS.pop(uid, None)
        ACTIVE.pop(uid, None)
        shutil.rmtree(work_dir, ignore_errors=True)

@app.on_message(filters.private & MEDIA_FILTER, group=-1)
async def merge_collect_handler(client, message):
    uid = message.from_user.id
    if is_archive_waiting(uid):
        return
    if uid not in MERGE_SESSIONS:
        return
    media = message.video or message.document
    if not media or (message.document and not (media.mime_type or "").startswith("video/")):
        return await message.reply_text("Merge mode mein sirf video files bhejo.")
    MERGE_SESSIONS[uid].append(message)
    await message.reply_text(f"Added part {len(MERGE_SESSIONS[uid])}. Send next video or /done.")

PENDING_RENAMES = {}

async def telegram_api(method, payload):
    import aiohttp
    url = "https://api.telegram.org/bot" + Config.BOT_TOKEN + "/" + method
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as response:
            result = await response.json()
            if not result.get("ok"):
                raise RuntimeError(result.get("description", "Telegram API error"))
            return result.get("result")

async def process_rename_file(client, message, new_name, output_type):
    user_id = message.from_user.id
    media = message.document or message.video or message.audio or message.animation
    if not media:
        return
    status = await message.reply_text("Preparing download…")
    work_dir = tempfile.mkdtemp(prefix="zura_", dir=Config.DOWNLOAD_DIR)
    ACTIVE[user_id] = asyncio.current_task()
    started = time.monotonic()
    last = [0.0]
    try:
        local_path = await client.download_media(
            message, file_name=f"{work_dir}/",
            progress=lambda current, total: update_progress(status, "Downloading", current, total, started, last)
        )
        if not local_path or not os.path.isfile(local_path):
            return await status.edit_text("Download failed.")
        renamed_path = os.path.join(work_dir, new_name)
        os.replace(local_path, renamed_path)

        caption_template = await settings.get_value(user_id, "caption")
        if caption_template:
            caption = caption_template.format(
                filename=os.path.splitext(new_name)[0],
                ext=os.path.splitext(new_name)[1].lstrip("."),
                user_id=user_id
            )
        else:
            # Keep the incoming caption; if none exists, show the renamed filename as the video caption.
            caption = (message.caption or "").strip() or new_name


        meta_enabled = await settings.get_value(user_id, "meta_enabled", False)
        metadata_values = {
            "title": await settings.get_value(user_id, "meta_title"),
            "author": await settings.get_value(user_id, "meta_author"),
            "artist": await settings.get_value(user_id, "meta_artist"),
            "audio": await settings.get_value(user_id, "meta_audio"),
            "subtitle": await settings.get_value(user_id, "meta_subtitle"),
            "video": await settings.get_value(user_id, "meta_video"),
        }
        if meta_enabled and any(metadata_values.values()):
            if shutil.which("ffmpeg"):
                from media import write_metadata
                metadata_path = os.path.join(work_dir, "metadata_" + new_name)
                await write_metadata(renamed_path, metadata_path, **metadata_values)
                os.replace(metadata_path, renamed_path)
            else:
                log.warning("FFmpeg not found; custom metadata skipped")

        thumb_path = None
        thumb_id = await settings.get_value(user_id, "thumb_file_id")
        if thumb_id:
            try:
                thumb_path = await client.download_media(thumb_id, file_name=os.path.join(work_dir, "custom_thumb.jpg"))
            except Exception:
                log.warning("Could not download saved thumbnail for user %s", user_id, exc_info=True)
        if not thumb_path:
            original_thumbs = getattr(media, "thumbs", None) or []
            if original_thumbs:
                original_thumb = max(original_thumbs, key=lambda item: (getattr(item, "width", 0) or 0) * (getattr(item, "height", 0) or 0))
                try:
                    thumb_path = await client.download_media(original_thumb.file_id, file_name=os.path.join(work_dir, "original_thumb.jpg"))
                    if thumb_path and os.path.getsize(thumb_path) > 200 * 1024:
                        os.remove(thumb_path)
                        thumb_path = None
                except Exception:
                    log.warning("Could not download original Telegram thumbnail", exc_info=True)
                    thumb_path = None
        is_video = bool(message.video or (message.document and (media.mime_type or "").startswith("video/")))
        if not thumb_path and is_video and shutil.which("ffmpeg"):
            try:
                from media import generate_thumbnail
                thumb_path = str(await generate_thumbnail(renamed_path, os.path.join(work_dir, "auto_thumb.jpg")))
            except Exception:
                log.warning("Automatic thumbnail generation failed for user %s", user_id, exc_info=True)

        started, last[0] = time.monotonic(), 0.0
        await status.edit_text("Preparing upload…")
        upload_thumb = thumb_path if thumb_path and os.path.isfile(thumb_path) else None
        upload_progress = lambda current, total: update_progress(status, "Uploading video" if output_type == "video" else "Uploading document", current, total, started, last)
        if output_type == "video":
            if not is_video:
                raise ValueError("This file is not a video. Choose Document output.")
            await client.send_video(
                chat_id=message.chat.id, video=renamed_path, caption=caption or None,
                thumb=upload_thumb, supports_streaming=True, reply_to_message_id=message.id,
                progress=upload_progress
            )
        else:
            await client.send_document(
                chat_id=message.chat.id, document=renamed_path, caption=caption or None,
                thumb=upload_thumb, reply_to_message_id=message.id, progress=upload_progress
            )
        await status.delete()
    except asyncio.CancelledError:
        try: await status.edit_text("Job cancelled.")
        except Exception: pass
        raise
    except Exception as exc:
        log.exception("Rename operation failed for user %s", user_id)
        try: await status.edit_text("Rename failed: " + str(exc)[:450])
        except Exception: pass
    finally:
        ACTIVE.pop(user_id, None)
        shutil.rmtree(work_dir, ignore_errors=True)

@app.on_message(filters.private & MEDIA_FILTER)
async def rename_file_handler(client, message):
    user_id = message.from_user.id
    if is_archive_waiting(user_id) or user_id in MERGE_SESSIONS:
        return
    if user_id in ACTIVE and not ACTIVE[user_id].done():
        return await message.reply_text("A job is already running. Use /cancel first.")
    media = message.document or message.video or message.audio or message.animation
    if not media:
        return
    original_name = getattr(media, "file_name", None) or f"zura_file_{media.file_unique_id}"
    PENDING_RENAMES[user_id] = {"message": message, "original_name": original_name}
    await message.reply_text(
        "Please Enter New Filename…\n\nOld File Name :- " + original_name +
        "\n\nSend the new filename (with or without extension). Use /cancel to stop."
    )

@app.on_message(filters.private & filters.text, group=-1)
async def rename_filename_input_handler(client, message):
    user_id = message.from_user.id
    pending = PENDING_RENAMES.get(user_id)
    if not pending or message.text.startswith("/"):
        return
    raw_name = message.text.strip().replace("\\", "/").split("/")[-1]
    if not raw_name or raw_name in (".", ".."):
        return await message.reply_text("Please send a valid filename.")
    original_name = pending["original_name"]
    original_ext = os.path.splitext(original_name)[1]
    if not os.path.splitext(raw_name)[1] and original_ext:
        raw_name += original_ext
    if len(raw_name.encode("utf-8")) > 240:
        return await message.reply_text("Filename is too long. Please use a shorter name.")
    if any(ch in raw_name for ch in ("\0", "\n", "\r")):
        return await message.reply_text("Filename contains invalid characters.")
    prefix = await settings.get_value(message.from_user.id, "filename_prefix", "")\n    if prefix and not raw_name.startswith(prefix):\n        raw_name = prefix + raw_name\n    pending["new_name"] = raw_name
    prompt = await message.reply_text(
        "Select The Output File Type\n\nFile Name :- " + raw_name
    )
    await telegram_api("editMessageReplyMarkup", {
        "chat_id": prompt.chat.id, "message_id": prompt.id,
        "reply_markup": {"inline_keyboard": [
            [{"text": "⭐ 📁 Document", "callback_data": "zura:output:document", "style": "primary"}],
            [{"text": "🎥 Video", "callback_data": "zura:output:video", "style": "success"}]
        ]}
    })

@app.on_callback_query(filters.regex(r"^zura:output:(document|video)$"))
async def rename_output_type_callback(client, query):
    user_id = query.from_user.id
    pending = PENDING_RENAMES.get(user_id)
    if not pending:
        return await query.answer("This rename request has expired.", show_alert=True)
    output_type = query.data.rsplit(":", 1)[1]
    source = pending["message"]
    new_name = pending.get("new_name")
    if not new_name:
        return await query.answer("Please enter the new filename first.", show_alert=True)
    PENDING_RENAMES.pop(user_id, None)
    await query.answer("Starting " + output_type + " upload…")
    try:
        await telegram_api("editMessageReplyMarkup", {
            "chat_id": query.message.chat.id, "message_id": query.message.id,
            "reply_markup": {"inline_keyboard": []}
        })
    except Exception:
        pass
    if user_id in ACTIVE and not ACTIVE[user_id].done():
        return await query.message.reply_text("Another task is already running. Use /cancel first.")
    task = asyncio.create_task(process_rename_file(client, source, new_name, output_type))
    ACTIVE[user_id] = task


register_archive_handlers(app, Config)
register_settings_handlers(app, Config, settings)

if __name__ == "__main__":
    app.run()
