import logging
import os
import shutil
import tempfile

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from config import Config
from database import UserSettings
from rename_engine import build_filename

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("zura")

os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)
app = Client(
    "zura_rename",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    parse_mode=ParseMode.DISABLED,
)
settings = UserSettings(Config.DB_URL, Config.DB_NAME)
MEDIA_FILTER = filters.document | filters.video | filters.audio | filters.animation


@app.on_message(filters.private & filters.command(["start", "help"]))
async def start_handler(client: Client, message: Message):
    await message.reply_text(
        "👋 ZuraRename Bot\n\n"
        "Send /autorenname <format> to set your rename template.\n"
        "Then send a document, video, audio, or animation.\n\n"
        "Placeholders:\n"
        "{filename} — original name without extension\n"
        "{ext} — original extension (without dot)\n"
        "{user_id} — your Telegram user ID\n"
        "{date} — current date (YYYY-MM-DD)\n"
        "{time} — current time (HH-MM-SS)\n\n"
        "Example:\n/autorenname NETQUBO - {filename} - {user_id}\n\n"
        "Commands: /myformat, /resetformat"
    )


@app.on_message(filters.private & filters.command(["autorenname", "autorename"]))
async def set_format_handler(client: Client, message: Message):
    if len(message.command) < 2:
        try:
            current = await settings.get_template(message.from_user.id)
        except Exception:
            log.exception("Could not read user template")
            return await message.reply_text("Database error. Please try again later.")
        suffix = f"\n\nCurrent format: {current}" if current else ""
        return await message.reply_text(
            "Send a format after the command.\n"
            "Example: /autorenname NETQUBO - {filename}" + suffix
        )

    template = message.text.split(maxsplit=1)[1].strip()
    if not template:
        return await message.reply_text("The format cannot be empty.")
    if len(template) > 180:
        return await message.reply_text("Template is too long. Keep it under 180 characters.")

    try:
        # Validate placeholder names before saving the template.
        build_filename(template, "example.mkv", message.from_user.id)
        await settings.set_template(message.from_user.id, template)
    except ValueError as exc:
        return await message.reply_text(f"Invalid format: {exc}")
    except Exception:
        log.exception("Could not save rename template")
        return await message.reply_text("Database error. Please check the connection and try again.")

    await message.reply_text(f"Rename format saved:\n{template}\n\nNow send your file.")


@app.on_message(filters.private & filters.command("myformat"))
async def my_format_handler(client: Client, message: Message):
    try:
        template = await settings.get_template(message.from_user.id)
    except Exception:
        log.exception("Could not read user template")
        return await message.reply_text("Database error. Please try again later.")
    if not template:
        return await message.reply_text("No format saved. Use /autorenname <format> first.")
    await message.reply_text(f"Your current format:\n{template}")


@app.on_message(filters.private & filters.command("resetformat"))
async def reset_format_handler(client: Client, message: Message):
    try:
        await settings.reset_template(message.from_user.id)
    except Exception:
        log.exception("Could not reset user template")
        return await message.reply_text("Database error. Please try again later.")
    await message.reply_text("Your rename format has been reset.")


@app.on_message(filters.private & MEDIA_FILTER)
async def rename_file_handler(client: Client, message: Message):
    user_id = message.from_user.id
    try:
        template = await settings.get_template(user_id)
    except Exception:
        log.exception("Could not read template for user %s", user_id)
        return await message.reply_text("Database error. Please try again later.")

    if not template:
        return await message.reply_text("Please set a rename format using /autorenname first.")

    media = message.document or message.video or message.audio or message.animation
    if not media:
        return

    original_name = getattr(media, "file_name", None) or f"zura_file_{media.file_unique_id}"
    try:
        new_name = build_filename(template, original_name, user_id)
    except ValueError as exc:
        return await message.reply_text(f"Invalid filename format: {exc}")

    status = await message.reply_text("Downloading your file...")
    work_dir = tempfile.mkdtemp(prefix="zura_", dir=Config.DOWNLOAD_DIR)
    try:
        local_path = await client.download_media(message, file_name=f"{work_dir}/")
        if not local_path or not os.path.isfile(local_path):
            return await status.edit_text("Download failed.")

        renamed_path = os.path.join(work_dir, new_name)
        os.replace(local_path, renamed_path)
        await status.edit_text("Uploading renamed file...")
        # Sending as a document keeps the renamed filename visible for every supported media type.
        await client.send_document(
            chat_id=message.chat.id,
            document=renamed_path,
            caption=message.caption or None,
            reply_to_message_id=message.id,
        )
        await status.delete()
    except Exception:
        log.exception("Rename operation failed for user %s", user_id)
        try:
            await status.edit_text("Rename failed. Check the bot logs and available disk space.")
        except Exception:
            pass
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    app.run()
