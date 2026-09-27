import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./razdelim.db",
)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_NAME = os.getenv("BOT_NAME", "razdelim_bot")
MAX_API_BASE = os.getenv("MAX_API_BASE", "https://platform-api.max.ru")
MAX_WEBHOOK_SECRET = os.getenv("MAX_WEBHOOK_SECRET", "")
MAX_INIT_DATA_MAX_AGE_SECONDS = int(os.getenv("MAX_INIT_DATA_MAX_AGE_SECONDS", "86400"))
