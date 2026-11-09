import os

class Config:
    API_ID = int(os.environ["API_ID"])
    API_HASH = os.environ["API_HASH"]
    BOT_TOKEN = os.environ["BOT_TOKEN"]
    DB_URL = os.environ["DB_URL"]
    DB_NAME = os.getenv("DB_NAME", "zura_rename")
    DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
