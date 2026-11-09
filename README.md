# ZuraRenamebot

An independently implemented Telegram auto-rename bot using Pyrogram and MongoDB.

## Features
- Per-user filename templates and extension preservation.
- Documents, videos, audio and animations.
- Custom output caption: `/setcaption your caption`; use `/delcaption` to clear.
- Custom thumbnail: reply to a photo with `/setthumb`; use `/delthumb` to clear.
- Download/upload progress and per-user job cancellation with `/cancel`.\n- Case-insensitive filename text replacement: `/setreplace OLD | NEW`, `/myreplace`, `/delreplace`.
- Optional FFmpeg helpers in `media.py` for media inspection and metadata remuxing.

## Commands
- `/start`, `/help`
- `/autorenname {filename}_{date}.{ext}`
- `/myformat`, `/resetformat`
- `/setcaption text`, `/delcaption`
- Reply to a photo with `/setthumb`; `/delthumb`
- `/setreplace OLD | NEW`, `/myreplace`, `/delreplace`\n- `/cancel`

## Placeholders
`{filename}`, `{ext}`, `{user_id}`, `{date}`, `{time}`.

## Setup
1. Copy `.env.example` to `.env` and fill Telegram credentials and MongoDB URI.
2. Install dependencies: `pip install -r requirements.txt`.
3. Run: `python bot.py`.

Install FFmpeg and ffprobe if you plan to use the optional helper module. Telegram bot file-size limits depend on the API environment and are not bypassed by this project.

This is an active development version. Test it with your deployment environment before public use.
