import aiohttp
from pyrogram import filters

def register_settings_handlers(app, Config, settings):
    pending = {}
    metadata_fields = {
        "title": ("Tɪᴛʟᴇ", "meta_title"),
        "author": ("Aᴜᴛʜᴏʀ", "meta_author"),
        "artist": ("Aʀᴛɪꜱᴛ", "meta_artist"),
        "audio": ("Aᴜᴅɪᴏ", "meta_audio"),
        "subtitle": ("Sᴜʙᴛɪᴛʟᴇ", "meta_subtitle"),
        "video": ("Vɪᴅᴇᴏ", "meta_video"),
    }

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

    async def metadata_markup(uid):
        rows = []
        for field, (label, key) in metadata_fields.items():
            value = await settings.get_value(uid, key, "")
            enabled = await settings.get_value(uid, "meta_" + field + "_enabled", bool(value))
            shown = (value[:18] + "…") if value and len(value) > 18 else (value or "Set")
            edit_text = f"◈ {label} · {shown}"
            toggle_text = "▹ ON" if enabled else "▹ OFF"
            toggle_style = "success" if enabled else "danger"
            rows.append([
                button(edit_text, "zset:meta_edit:" + field),
                button(toggle_text, "zset:meta_toggle:" + field, toggle_style)
            ])
        rows.append([button("🧹 Clear all", "zset:meta_clear", "danger"), button("⬅ Back", "zset:home")])
        return keyboard(rows)

    async def show_metadata(chat_id, message_id):
        enabled = await settings.get_value(chat_id, "meta_enabled", False)
        markup = await metadata_markup(chat_id)
        text = (
            "Mᴇᴛᴀᴅᴀᴛᴀ Sᴇᴛᴛɪɴɢꜱ\n\n"
            "Tap the left button to set/edit a value.\n"
            "Tap ON/OFF to enable or disable that field."
        )
        await api("editMessageText", {"chat_id": chat_id, "message_id": message_id,
            "text": text, "reply_markup": markup})

    def home_markup(meta_enabled):
        return keyboard([
            [button("📝 Rename Format", "zset:format"), button("🏷 Caption", "zset:caption")],
            [button("🖼 Thumbnail", "zset:thumb"), button("Mᴇᴛᴀᴅᴀᴛᴀ ▹", "zset:metadata")],
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
                pending.pop(uid, None)
                await show_home(chat_id, message_id)
                await query.answer()
                return
            if action == "metadata":
                await show_metadata(uid, message_id)
                await query.answer()
                return
            if action.startswith("meta_toggle:"):
                field = action.split(":", 1)[1]
                if field not in metadata_fields:
                    return await query.answer("Unknown metadata field", show_alert=True)
                key = "meta_" + field + "_enabled"
                current = await settings.get_value(uid, key, False)
                await settings.set_value(uid, key, not current)
                await show_metadata(uid, message_id)
                await query.answer(field.title() + (" enabled" if not current else " disabled"))
                return
            if action.startswith("meta_edit:"):
                field = action.split(":", 1)[1]
                if field not in metadata_fields:
                    return await query.answer("Unknown metadata field", show_alert=True)
                pending[uid] = "meta:" + field
                label, key = metadata_fields[field]
                current = await settings.get_value(uid, key, "")
                prompt = f"✏️ Sᴇᴛ {label}\n\nCurrent: {current or 'Not set'}\n\nSend the new value. Send /cancel to cancel."
                await api("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                    "text": prompt, "reply_markup": keyboard([[button("⬅ Cancel / Back", "zset:metadata")]])})
                await query.answer()
                return
            if action == "meta_clear":
                for field, (label, key) in metadata_fields.items():
                    await settings.set_value(uid, key, None)
                    await settings.set_value(uid, "meta_" + field + "_enabled", False)
                await show_metadata(uid, message_id)
                await query.answer("All metadata cleared")
                return
            if action == "show":
                fields = [("Rename format", "rename_template"), ("Caption", "caption"),
                          ("Thumbnail", "thumb_file_id"), ("Prefix", "filename_prefix")]
                lines = []
                for label, key in fields:
                    value = await settings.get_value(uid, key)
                    if key == "thumb_file_id":
                        value = "Set" if value else "Not set"
                    lines.append(label + ": " + str(value or "Not set"))
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
            if action.startswith("meta:"):
                field = action.split(":", 1)[1]
                label, key = metadata_fields[field]
                if not value:
                    return await message.reply_text("Value cannot be empty.")
                await settings.set_value(uid, key, value)
                await settings.set_value(uid, "meta_" + field + "_enabled", True)
                pending.pop(uid, None)
                try:
                    await api("deleteMessage", {"chat_id": message.chat.id, "message_id": message.id})
                except Exception:
                    pass
                await message.reply_text("✅ " + label + " saved")
                await show_home(message.chat.id)
                return
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
