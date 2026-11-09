# ZuraRenamebot

An independently written Telegram auto-rename bot starter.

## Features
- Per-user filename templates
- Preserve original file extensions
- Rename and re-upload supported Telegram media
- MongoDB-backed user settings

## Setup
1. Copy `.env.example` to `.env` and fill in your Telegram credentials and MongoDB URI.
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `python bot.py`

Template placeholders: `{filename}`, `{ext}`, `{user_id}`, `{date}`, `{time}`.

This is a starter project; test it with your deployment environment and Telegram file-size limits before production use.

## License
MIT. See [LICENSE](LICENSE).
