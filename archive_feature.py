import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ZIP and 7Z archives are handled by Python libraries. RAR extraction needs
# the system 7z executable; output is rebuilt as 7Z because RAR creation is
# not supported by the free tools used here.
WAITING = {}
SESSIONS = {}

def register_archive_handlers(app, Config):
    async def stop(update):
        try:
            await update.stop_propagation()
        except Exception:
            pass

    async def ask_password(client, message, state):
        state["stage"] = "old_password"
        await message.reply_text(
            "Archive download complete.\nSend its current password.\n"
            "If it has no password, send /skip.\nUse /cancel to stop."
        )

    @app.on_message(filters.private & filters.command("archive"), group=-1)
    async def archive_command(client, message):
        uid = message.from_user.id
        if uid in WAITING or uid in SESSIONS:
            return await message.reply_text("Archive task already active. Send /cancel first.")
        WAITING[uid] = {"stage": "file"}
        await message.reply_text(
            "🔐 Archive password tool\n\n"
            "Now send a .zip, .7z or .rar file.\n"
            "I can remove/change a password only when you know the current password.\n"
            "RAR files are rebuilt as .7z."
        )
        await stop(message)

    @app.on_message(filters.private & filters.command("skip"), group=-1)
    async def archive_skip(client, message):
        uid = message.from_user.id
        state = WAITING.get(uid)
        if not state or state.get("stage") != "old_password":
            return
        state["old_password"] = None
        state["stage"] = "action"
        await message.reply_text(
            "Choose what to do:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Remove password", callback_data="zarch:remove"),
                 InlineKeyboardButton("Change password", callback_data="zarch:change")]
            ])
        )
        await stop(message)

    @app.on_message(filters.private & filters.command("cancel"), group=-1)
    async def archive_cancel(client, message):
        uid = message.from_user.id
        state = WAITING.pop(uid, None) or SESSIONS.pop(uid, None)
        if state:
            shutil.rmtree(state.get("work_dir", ""), ignore_errors=True)
            await message.reply_text("Archive task cancelled.")
            await stop(message)

    @app.on_message(filters.private & filters.text, group=-1)
    async def archive_text(client, message):
        uid = message.from_user.id
        state = WAITING.get(uid)
        if not state:
            return
        stage = state.get("stage")
        if stage == "old_password":
            state["old_password"] = message.text
            state["stage"] = "action"
            try:
                await message.delete()
            except Exception:
                pass
            await message.reply_text(
                "Choose what to do:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Remove password", callback_data="zarch:remove"),
                     InlineKeyboardButton("Change password", callback_data="zarch:change")]
                ])
            )
            await stop(message)
        elif stage == "new_password":
            if len(message.text) < 1:
                return await message.reply_text("Password cannot be empty.")
            state["new_password"] = message.text
            try:
                await message.delete()
            except Exception:
                pass
            await process_archive(client, message, uid, state, change=True)
            await stop(message)

    async def process_archive(client, message, uid, state, change=False):
        work = state["work_dir"]
        src = state["path"]
        ext = Path(src).suffix.lower()
        password = state.get("old_password")
        new_password = state.get("new_password")
        status = await message.reply_text("Processing archive…")
        extract_dir = os.path.join(work, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        try:
            if ext == ".zip":
                import pyzipper
                with pyzipper.AESZipFile(src) as zf:
                    if password:
                        zf.setpassword(password.encode())
                    zf.extractall(path=extract_dir)
                output = os.path.join(work, Path(src).stem + ("_protected.zip" if change else "_unlocked.zip"))
                with pyzipper.AESZipFile(output, "w", compression=pyzipper.ZIP_DEFLATED) as zf:
                    if change:
                        zf.setencryption(pyzipper.WZ_AES, nbits=256)
                        zf.setpassword(new_password.encode())
                    for root, _, files in os.walk(extract_dir):
                        for name in files:
                            full = os.path.join(root, name)
                            zf.write(full, os.path.relpath(full, extract_dir))
            elif ext == ".7z":
                import py7zr
                with py7zr.SevenZipFile(src, mode="r", password=password) as zf:
                    zf.extractall(path=extract_dir)
                output = os.path.join(work, Path(src).stem + ("_protected.7z" if change else "_unlocked.7z"))
                with py7zr.SevenZipFile(output, mode="w", password=new_password if change else None,
                                        header_encryption=bool(change)) as zf:
                    for root, _, files in os.walk(extract_dir):
                        for name in files:
                            full = os.path.join(root, name)
                            zf.write(full, os.path.relpath(full, extract_dir))
            elif ext == ".rar":
                seven = shutil.which("7z") or shutil.which("7zz")
                if not seven:
                    raise RuntimeError("RAR support needs 7z installed on the hosting system.")
                cmd = [seven, "x", "-y", f"-o{extract_dir}", f"-p{password or ''}", src]
                proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL,
                                                             stderr=asyncio.subprocess.PIPE)
                _, err = await proc.communicate()
                if proc.returncode:
                    raise RuntimeError(err.decode(errors="replace")[-500:] or "Wrong password or damaged archive.")
                import py7zr
                output = os.path.join(work, Path(src).stem + ("_protected.7z" if change else "_unlocked.7z"))
                with py7zr.SevenZipFile(output, mode="w", password=new_password if change else None,
                                        header_encryption=bool(change)) as zf:
                    for root, _, files in os.walk(extract_dir):
                        for name in files:
                            full = os.path.join(root, name)
                            zf.write(full, os.path.relpath(full, extract_dir))
            else:
                raise RuntimeError("Supported formats: ZIP, 7Z and RAR.")
            if not os.path.isfile(output) or os.path.getsize(output) == 0:
                raise RuntimeError("Output archive was not created.")
            await client.send_document(message.chat.id, output,
                                       caption="🔐 Password changed." if change else "🔓 Password removed.")
            await status.delete()
        except Exception as exc:
            await status.edit_text(f"Archive failed: {str(exc)[:700]}\nCheck the current password and archive integrity.")
        finally:
            WAITING.pop(uid, None)
            SESSIONS.pop(uid, None)
            shutil.rmtree(work, ignore_errors=True)

    @app.on_callback_query(filters.regex(r"^zarch:(remove|change)$"), group=-1)
    async def archive_action(client, query):
        uid = query.from_user.id
        state = WAITING.get(uid)
        if not state or state.get("stage") != "action":
            return await query.answer("This archive session has expired.", show_alert=True)
        if query.data.endswith("change"):
            state["stage"] = "new_password"
            await query.message.edit_text("Send the new archive password as a message. It will be deleted after receiving.")
            await query.answer()
        else:
            await query.answer("Removing password…")
            await process_archive(client, query.message, uid, state, change=False)
        await stop(query)

    @app.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.animation), group=-1)
    async def archive_file(client, message):
        uid = message.from_user.id
        state = WAITING.get(uid)
        if not state or state.get("stage") != "file":
            return
        media = message.document or message.video or message.audio or message.animation
        name = getattr(media, "file_name", None) or ""
        ext = Path(name).suffix.lower()
        if ext not in (".zip", ".7z", ".rar"):
            await message.reply_text("Unsupported archive. Send a .zip, .7z or .rar file.")
            await stop(message)
            return
        work = tempfile.mkdtemp(prefix="zura_archive_", dir=Config.DOWNLOAD_DIR)
        state["work_dir"] = work
        state["path"] = os.path.join(work, name or "archive" + ext)
        status = await message.reply_text("Downloading archive…")
        try:
            path = await client.download_media(message, file_name=state["path"])
            if not path or not os.path.isfile(path):
                raise RuntimeError("Download failed.")
            state["path"] = path
            await ask_password(client, message, state)
            await status.delete()
        except Exception as exc:
            WAITING.pop(uid, None)
            shutil.rmtree(work, ignore_errors=True)
            await status.edit_text(f"Could not download archive: {str(exc)[:400]}")
        await stop(message)
