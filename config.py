import os
from dotenv import load_dotenv

load_dotenv()

_REQUIRED = ("API_ID", "API_HASH", "BOT_TOKEN", "DB_URL")
_missing = [key for key in _REQUIRED if not os.getenv(key)]
if _missing:
    raise RuntimeError("Missing required environment variables: " + ", ".join(_missing))

try:
    _api_id = int(os.environ["API_ID"])
except ValueError as exc:
    raise RuntimeError("API_ID must be a number.") from exc


class Config:
    API_ID = _api_id
    API_HASH = os.environ["API_HASH"]
    BOT_TOKEN = os.environ["BOT_TOKEN"]
    DB_URL = os.environ["DB_URL"]
    DB_NAME = os.getenv("DB_NAME", "zura_rename")
    DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
