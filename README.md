# ZuraRenamebot

An independently implemented Telegram auto-rename bot built with Pyrogram and MongoDB.

## Current features
- Per-user rename templates with safe filename sanitization.
- Preserves the original file extension.
- Supports documents, videos, audio and animations.
- MongoDB-backed user settings.
- Optional FFmpeg helpers for inspecting media and writing container metadata without re-encoding.

## Template placeholders
`{filename}`, `{ext}`, `{user_id}`, `{date}`, and `{time}`.

## Setup
1. Copy `.env.example` to `.env` and fill in Telegram credentials and MongoDB URI.
2. Install dependencies: `pip install -r requirements.txt`.
3. Run: `python bot.py`.

Install FFmpeg (including ffprobe) on the host to use the optional media helper module.

This project is independently implemented. Test with your deployment environment and Telegram file-size limits before production use.

## License
MIT. See [LICENSE](LICENSE).
