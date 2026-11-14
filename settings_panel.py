import aiohttp
from pyrogram import filters

def register_settings_handlers(app, Config, settings):
    pending = {}

    def keyboard(rows):
        return {"inline_keyboard": rows}

    def button(text, data, style="primary"):
        return {"text": text, "callback_data": data, "style": style}

    async def api(method, payload):
        url = "https://api.telegram.org/bot" + Config.BOT_TOKEN + "/" + method
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                result = await response.json()
                if not result.get("ok"):
                    raise RuntimeError(result.get("description", "Telegram Bot API error"))
                return result.get("result")

    def home_markup(meta_enabled):
        meta_text = "Metadata: ON" if meta_enabled else "Metadata: OFF"
        meta_style = "success" if meta_enabled else "danger"
        return keyboard([
            [button("📝 Rename Format", "zset:format"), button("🏷 Caption", "zset:caption")],
            [button("🖼 Thumbnail", "zset:thumb"), button(meta_text, "zset:metadata", meta_style)],
            [button("🔄 Text Replace", "zset:replace"), button("🔐 Archive Tool", "zset:archive")],
            [button("📊 My Settings", "zset:show", "success"), button("✖ Close", "zset:close", "danger")]
        ])

    async def show_home(chat_id, message_id=None):
        enabled = await settings.get_value(chat_id, "meta_enabled", False)
        payload = {
            "chat_id": chat_id,
            "text": "⚙️ ZuraRenamebot Settings\n\nChoose a setting below. Changes are saved to your account.",
            "reply_markup": home_markup(enabled)
        }
        if message_id:
            payload["message_id"] = message_id
            await api("editMessageText", payload)
        else:
            await api("sendMessage", payload)

    @app.on_message(filters.private & filters.command("settings"))
    async def settings_command(client, message):
        try:
            await show_home(message.chat.id)
        except Exception as exc:
            await message.reply_text("Could not open settings: " + str(exc)[:250])

    @app.on_callback_query(filters.regex(r"^zset:"), group=-2)
    async def settings_callback(client, query):
        uid = query.from_user.id
        action = query.data.split(":", 1)[1]
        chat_id = query.message.chat.id
        message_id = query.message.id
        try:
            if action == "close":
                await api("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": "Settings closed."})
                await query.answer("Closed")
                return
            if action == "home":
                await show_home(chat_id, message_id)
                await query.answer()
                return
            if action == "metadata":
                current = await settings.get_value(uid, "meta_enabled", False)
                await settings.set_value(uid, "meta_enabled", not current)
                await show_home(chat_id, message_id)
                await query.answer("Metadata " + ("enabled" if not current else "disabled"))
                return
            if action == "show":
                fields = [("Rename format", "rename_template"), ("Caption", "caption"),
                          ("Thumbnail", "thumb_file_id"), ("Replace from", "replace_from"),
                          ("Replace to", "replace_to")]
                lines = []
                for label, key in fields:
                    value = await settings.get_value(uid, key)
                    if key == "thumb_file_id":
                        value = "Set" if value else "Not set"
                    lines.append(label + ": " + str(value or "Not set"))
                enabled = await settings.get_value(uid, "meta_enabled", False)
                lines.append("Metadata: " + ("ON" if enabled else "OFF"))
                await api("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                    "text": "📊 Your Settings\n\n" + "\n".join(lines),
                    "reply_markup": keyboard([[button("⬅ Back", "zset:home", "primary")]])})
                await query.answer()
                return
            if action in ("format", "caption", "thumb", "replace"):
                pending[uid] = action
                prompts = {
                    "format": "Send your new rename format. Example: {filename}_{date}.{ext}\nUse /cancel to stop.",
                    "caption": "Send your new caption. Use /delcaption to clear it, or /cancel to stop.",
                    "thumb": "Send a photo, then reply to it with /setthumb. Use /delthumb to remove it.",
                    "replace": "Send replacement in this format: OLD TEXT | NEW TEXT\nUse /cancel to stop."
                }
                await api("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                    "text": prompts[action],
                    "reply_markup": keyboard([[button("⬅ Back", "zset:home", "primary")]])})
                await query.answer()
                return
            if action == "archive":
                await api("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                    "text": "🔐 Archive Password Tool\n\nSend /archive to remove or change a ZIP, 7Z or RAR password. You must know the current password.",
                    "reply_markup": keyboard([[button("⬅ Back", "zset:home", "primary")]])})
                await query.answer()
                return
            await query.answer("Unknown setting", show_alert=True)
        except Exception as exc:
            await query.answer(str(exc)[:180], show_alert=True)

    @app.on_message(filters.private & filters.text, group=-3)
    async def settings_text_input(client, message):
        uid = message.from_user.id
        action = pending.get(uid)
        if not action or message.text.startswith("/"):
            return
        value = message.text.strip()
        try:
            if action == "format":
                from rename_engine import build_filename
                build_filename(value, "example.mkv", uid)
                await settings.set_value(uid, "rename_template", value)
                reply = "Rename format saved."
            elif action == "caption":
                await settings.set_value(uid, "caption", value)
                reply = "Caption saved."
            elif action == "replace":
                if "|" not in value:
                    return await message.reply_text("Use this format: OLD TEXT | NEW TEXT")
                old, new = (part.strip() for part in value.split("|", 1))
                if not old:
                    return await message.reply_text("OLD TEXT cannot be empty.")
                await settings.set_value(uid, "replace_from", old)
                await settings.set_value(uid, "replace_to", new)
                reply = "Text replacement saved."
            else:
                return
            pending.pop(uid, None)
            await message.reply_text(reply)
            await show_home(message.chat.id)
        except Exception as exc:
            await message.reply_text("Could not save setting: " + str(exc)[:250])
