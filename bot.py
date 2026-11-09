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

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("zura")
os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)

app = Client("zura_rename", api_id=Config.API_ID, api_hash=Config.API_HASH,
             bot_token=Config.BOT_TOKEN, parse_mode=ParseMode.DISABLED,\n             workers=Config.WORKERS,\n             max_concurrent_transmissions=Config.MAX_CONCURRENT_TRANSMISSIONS)
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
    percent = min(100.0, current * 100 / total) if total else 0
    filled = min(12, int(percent / 100 * 12))
    speed = current / max(time.monotonic() - started, 0.1)
    eta = int((total - current) / speed) if speed and total else 0
    return (f"**{label}**\\n"
            f"{'▰' * filled}{'▱' * (12 - filled)} {percent:.1f}%\\n"
            f"📦 {human(current)} / {human(total)}\\n"
            f"⚡ {human(speed)}/s  •  ⏳ ETA: {eta}s")

async def update_progress(status, label, current, total, started, last):
    now = time.monotonic()
    if now - last[0] < 2 and current < total:
        return
    last[0] = now
    try:
        await status.edit_text(progress_text(label, current, total, started))
    except Exception:
        pass

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
        "/setreplace OLD | NEW — replace text in filenames\\n"
        "/myreplace — show replacement\\n/delreplace — remove replacement\\n"
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

@app.on_message(filters.private & filters.command("setreplace"))
async def set_replace_handler(client, message):
    raw = message.text.split(maxsplit=1)[1] if len(message.command) > 1 else ""
    if "|" not in raw:
        return await message.reply_text("Usage: /setreplace OLD TEXT | NEW TEXT\\nExample: /setreplace @ASKOREANDRAMA | @MYCHANNEL")
    old, new = (part.strip() for part in raw.split("|", 1))
    if not old:
        return await message.reply_text("The text to find cannot be empty.")
    await settings.set_value(message.from_user.id, "replace_from", old)
    await settings.set_value(message.from_user.id, "replace_to", new)
    await message.reply_text(f"Filename replacement saved:\\n{old} → {new}\\nIt will apply to matching filenames you send.")

@app.on_message(filters.private & filters.command("myreplace"))
async def my_replace_handler(client, message):
    old = await settings.get_value(message.from_user.id, "replace_from")
    new = await settings.get_value(message.from_user.id, "replace_to", "")
    if not old:
        return await message.reply_text("No filename replacement is set. Use /setreplace OLD | NEW.")
    await message.reply_text(f"Current replacement:\\n{old} → {new}")

@app.on_message(filters.private & filters.command("delreplace"))
async def delete_replace_handler(client, message):
    await settings.set_value(message.from_user.id, "replace_from", None)
    await settings.set_value(message.from_user.id, "replace_to", None)
    await message.reply_text("Filename replacement removed.")

@app.on_message(filters.private & filters.command("cancel"))
async def cancel_handler(client, message):
    uid = message.from_user.id
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
        replace_from = await settings.get_value(uid, "replace_from")
        replace_to = await settings.get_value(uid, "replace_to", "")
        if replace_from:
            import re
            base, suffix = os.path.splitext(output_name)
            output_name = re.sub(re.escape(replace_from), lambda _: replace_to or "", base, flags=re.IGNORECASE).strip() + suffix
        output_path = os.path.join(work_dir, output_name)
        await status.edit_text("Merging video parts…")
        await merge_videos(local_files, output_path)
        caption = await settings.get_value(uid, "caption")
        if caption:
            caption = caption.format(filename=os.path.splitext(output_name)[0], ext=os.path.splitext(output_name)[1].lstrip("."), user_id=uid)
        started, last = time.monotonic(), [0.0]
        await status.edit_text("Uploading merged video…")
        await client.send_document(
            chat_id=message.chat.id, document=output_path, caption=caption or None,
            reply_to_message_id=message.id,
            progress=lambda current, total: update_progress(status, "Uploading merged file", current, total, started, last)
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

@app.on_message(filters.private & MEDIA_FILTER)
async def merge_collect_handler(client, message):
    uid = message.from_user.id
    if uid not in MERGE_SESSIONS:
        return
    media = message.video or message.document
    if not media or (message.document and not (media.mime_type or "").startswith("video/")):
        return await message.reply_text("Merge mode mein sirf video files bhejo.")
    MERGE_SESSIONS[uid].append(message)
    await message.reply_text(f"Added part {len(MERGE_SESSIONS[uid])}. Send next video or /done.")

@app.on_message(filters.private & MEDIA_FILTER)
async def rename_file_handler(client, message):
    user_id = message.from_user.id
    if user_id in ACTIVE and not ACTIVE[user_id].done():
        return await message.reply_text("A job is already running. Use /cancel first.")
    # If the user has not chosen a custom format, preserve the original filename automatically.
    template = await settings.get_value(user_id, "rename_template") or "{filename}.{ext}"
    media = message.document or message.video or message.audio or message.animation
    if not media:
        return
    original_name = getattr(media, "file_name", None) or f"zura_file_{media.file_unique_id}"
    replace_from = await settings.get_value(user_id, "replace_from")
    replace_to = await settings.get_value(user_id, "replace_to", "")
    try:
        new_name = build_filename(template, original_name, user_id)
        # Apply replacement after rendering so fixed text in /autorenname is handled too.
        if replace_from:
            stem, extension = os.path.splitext(new_name)
            stem = __import__("re").sub(__import__("re").escape(replace_from),
                lambda _: replace_to or "", stem, flags=__import__("re").IGNORECASE)
            new_name = (stem.strip() or "renamed_file") + extension
    except ValueError as exc:
        return await message.reply_text(f"Invalid filename format: {exc}")

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
        caption = caption_template.format(filename=os.path.splitext(new_name)[0], ext=os.path.splitext(new_name)[1].lstrip("."), user_id=user_id) if caption_template else (message.caption or "")
        if replace_from and caption:
            caption = __import__("re").sub(__import__("re").escape(replace_from), lambda _: replace_to or "", caption, flags=__import__("re").IGNORECASE)
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

        # Priority: user's custom thumbnail > thumbnail attached to incoming Telegram file > FFmpeg preview.
        thumb_path = None
        thumb_id = await settings.get_value(user_id, "thumb_file_id")
        if thumb_id:
            try:
                thumb_path = await client.download_media(
                    thumb_id, file_name=os.path.join(work_dir, "custom_thumb.jpg")
                )
            except Exception:
                log.warning("Could not download saved thumbnail for user %s", user_id, exc_info=True)

        if not thumb_path:
            original_thumbs = getattr(media, "thumbs", None) or []
            if original_thumbs:
                # Choose the largest thumbnail Telegram supplied with the original media.
                original_thumb = max(
                    original_thumbs,
                    key=lambda item: (getattr(item, "width", 0) or 0) * (getattr(item, "height", 0) or 0)
                )
                try:
                    thumb_path = await client.download_media(
                        original_thumb.file_id, file_name=os.path.join(work_dir, "original_thumb.jpg")
                    )
                    if thumb_path and os.path.getsize(thumb_path) > 200 * 1024:
                        os.remove(thumb_path)
                        thumb_path = None
                except Exception:
                    log.warning("Could not download original Telegram thumbnail", exc_info=True)
                    thumb_path = None

        if not thumb_path and shutil.which("ffmpeg") and (
            message.video or (message.document and (media.mime_type or "").startswith("video/"))
        ):
            try:
                from media import generate_thumbnail
                thumb_path = str(await generate_thumbnail(
                    renamed_path, os.path.join(work_dir, "auto_thumb.jpg")
                ))
            except Exception:
                log.warning("Automatic thumbnail generation failed for user %s", user_id, exc_info=True)

        started = time.monotonic()
        last[0] = 0.0
        await status.edit_text("Preparing upload…")
        await client.send_document(
            chat_id=message.chat.id, document=renamed_path, caption=caption or None,
            thumb=thumb_path if thumb_path and os.path.isfile(thumb_path) else None,
            reply_to_message_id=message.id,
            progress=lambda current, total: update_progress(status, "Uploading", current, total, started, last)
        )
        await status.delete()
    except asyncio.CancelledError:
        try:
            await status.edit_text("Job cancelled.")
        except Exception:
            pass
        raise
    except Exception:
        log.exception("Rename operation failed for user %s", user_id)
        try:
            await status.edit_text("Rename failed. Check bot logs and available disk space.")
        except Exception:
            pass
    finally:
        ACTIVE.pop(user_id, None)
        shutil.rmtree(work_dir, ignore_errors=True)

if __name__ == "__main__":
    app.run()
