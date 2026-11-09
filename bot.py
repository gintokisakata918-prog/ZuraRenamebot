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
             bot_token=Config.BOT_TOKEN, parse_mode=ParseMode.DISABLED)
settings = UserSettings(Config.DB_URL, Config.DB_NAME)
MEDIA_FILTER = filters.document | filters.video | filters.audio | filters.animation
ACTIVE = {}

def human(size):
    size = float(size or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024

def progress_text(label, current, total, started):
    percent = current * 100 / total if total else 0
    filled = min(10, int(percent / 10))
    speed = current / max(time.monotonic() - started, 0.1)
    eta = int((total - current) / speed) if speed else 0
    return (f"{label}\n{'▰' * filled}{'▱' * (10 - filled)} {percent:.1f}%\n"
            f"{human(current)} / {human(total)}\n{human(speed)}/s • ETA {eta}s")

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
        "/cancel — cancel current rename job"
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
async def set_metadata_handler(client, message):
    raw = message.text.split(maxsplit=1)[1] if len(message.command) > 1 else ""
    parts = [part.strip() for part in raw.split("|")]
    if len(parts) != 3:
        return await message.reply_text(
            "Usage:\n/metadata Subtitle | Audio | Author\n"
            "Example:\n/metadata Sᴜʙᴛɪᴛʟᴇ | Aᴜᴅɪᴏ | NETQUBO"
        )
    subtitle, audio, author = parts
    await settings.set_value(message.from_user.id, "meta_subtitle", subtitle or None)
    await settings.set_value(message.from_user.id, "meta_audio", audio or None)
    await settings.set_value(message.from_user.id, "meta_author", author or None)
    await message.reply_text(
        f"Metadata saved:\nSubtitle: {subtitle or 'Not set'}\n"
        f"Audio: {audio or 'Not set'}\nAuthor: {author or 'Not set'}"
    )

@app.on_message(filters.private & filters.command("mymetadata"))
async def my_metadata_handler(client, message):
    subtitle = await settings.get_value(message.from_user.id, "meta_subtitle")
    audio = await settings.get_value(message.from_user.id, "meta_audio")
    author = await settings.get_value(message.from_user.id, "meta_author")
    if not any((subtitle, audio, author)):
        return await message.reply_text("No metadata settings saved. Use /metadata Subtitle | Audio | Author.")
    await message.reply_text(
        f"Current metadata:\nSubtitle: {subtitle or 'Not set'}\n"
        f"Audio: {audio or 'Not set'}\nAuthor: {author or 'Not set'}"
    )

@app.on_message(filters.private & filters.command("delmetadata"))
async def delete_metadata_handler(client, message):
    for key in ("meta_subtitle", "meta_audio", "meta_author"):
        await settings.set_value(message.from_user.id, key, None)
    await message.reply_text("Custom metadata settings removed.")

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
    task = ACTIVE.get(message.from_user.id)
    if task and not task.done():
        task.cancel()
        await message.reply_text("Cancellation requested.")
    else:
        await message.reply_text("No active rename job.")

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
        meta_subtitle = await settings.get_value(user_id, "meta_subtitle")
        meta_audio = await settings.get_value(user_id, "meta_audio")
        meta_author = await settings.get_value(user_id, "meta_author")
        if any((meta_subtitle, meta_audio, meta_author)):
            if shutil.which("ffmpeg"):
                from media import write_metadata
                metadata_path = os.path.join(work_dir, "metadata_" + new_name)
                await write_metadata(renamed_path, metadata_path,
                                     subtitle=meta_subtitle, audio=meta_audio, author=meta_author)
                os.replace(metadata_path, renamed_path)
            else:
                log.warning("FFmpeg not found; custom metadata skipped")
                thumb_id = await settings.get_value(user_id, "thumb_file_id")
        thumb_path = None
        if thumb_id:
            try:
                thumb_path = await client.download_media(thumb_id, file_name=f"{work_dir}/thumb.jpg")
            except Exception:
                log.warning("Could not download saved thumbnail for user %s", user_id, exc_info=True)

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
