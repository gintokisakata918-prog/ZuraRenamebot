import logging
import os
from pyrogram import Client, filters
from pyrogram.types import Message
from config import Config
from database import UserSettings
from rename_engine import build_filename

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("zura")

os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)
app = Client("zura_rename", api_id=Config.API_ID, api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN)
settings = UserSettings(Config.DB_URL, Config.DB_NAME)
MEDIA_FILTER = filters.document | filters.video | filters.audio | filters.animation

@app.on_message(filters.private & filters.command(["start", "help"]))
async def start_handler(client: Client, message: Message):
    await message.reply_text(
        "👋 **ZuraRename Bot**\n\n"
        "Send `/autorenname <format>` to set your rename template.\n"
        "Then send a document, video, audio, or animation.\n\n"
        "**Placeholders**\n"
        "`{filename}` — original name without extension\n"
        "`{ext}` — original extension (without dot)\n"
        "`{user_id}` — your Telegram user ID\n"
        "`{date}` — current date (YYYY-MM-DD)\n"
        "`{time}` — current time (HH-MM-SS)\n\n"
        "**Example**\n`/autorenname NETQUBO - {filename} - {user_id}`\n\n"
        "Commands: `/myformat`, `/resetformat`"
    )

@app.on_message(filters.private & filters.command(["autorenname", "autorename"]))
async def set_format_handler(client: Client, message: Message):
    if len(message.command) < 2:
        current = await settings.get_template(message.from_user.id)
        suffix = f"\n\nCurrent format: `{current}`" if current else ""
        return await message.reply_text("Send a format after the command.\nExample: `/autorenname NETQUBO - {filename}`" + suffix)
    template = message.text.split(maxsplit=1)[1].strip()
    if len(template) > 180:
        return await message.reply_text("Template is too long. Keep it under 180 characters.")
    try:
        await settings.set_template(message.from_user.id, template)
    except Exception:
        log.exception("Could not save rename template")
        return await message.reply_text("❌ Could not save your format. Check the database connection.")
    await message.reply_text(f"✅ **Rename format saved!**\n\n`{template}`\n\nNow send your file.")

@app.on_message(filters.private & filters.command("myformat"))
async def my_format_handler(client: Client, message: Message):
    template = await settings.get_template(message.from_user.id)
    if not template:
        return await message.reply_text("No format saved. Use `/autorenname <format>` first.")
    await message.reply_text(f"Your current format:\n`{template}`")

@app.on_message(filters.private & filters.command("resetformat"))
async def reset_format_handler(client: Client, message: Message):
    await settings.reset_template(message.from_user.id)
    await message.reply_text("Your rename format has been reset.")

@app.on_message(filters.private & MEDIA_FILTER)
async def rename_file_handler(client: Client, message: Message):
    user_id = message.from_user.id
    template = await settings.get_template(user_id)
    if not template:
        return await message.reply_text("Please set a rename format using `/autorenname` first.")
    media = message.document or message.video or message.audio or message.animation
    original_name = getattr(media, "file_name", None) or f"zura_file_{media.file_unique_id}"
    try:
        new_name = build_filename(template, original_name, user_id)
    except ValueError as exc:
        return await message.reply_text(f"❌ {exc}")
    status = await message.reply_text("⏳ Downloading your file...")
    local_path = None
    try:
        local_path = await client.download_media(message, file_name=f"{Config.DOWNLOAD_DIR}/")
        if not local_path:
            return await status.edit_text("❌ Download failed.")
        await status.edit_text("📤 Uploading renamed file...")
        await client.send_document(
            chat_id=message.chat.id, document=local_path, file_name=new_name,
            caption=message.caption or None, reply_to_message_id=message.id
        )
        await status.delete()
    except Exception:
        log.exception("Rename operation failed for user %s", user_id)
        await status.edit_text("❌ Rename failed. Check the bot logs and file size.")
    finally:
        if local_path and os.path.isfile(local_path):
            try:
                os.remove(local_path)
            except OSError:
                log.warning("Could not remove temporary file: %s", local_path)

if __name__ == "__main__":
    app.run()
