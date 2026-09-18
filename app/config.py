import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://razdelim:razdelim@localhost:5432/razdelim",
)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_NAME = os.getenv("BOT_NAME", "razdelim_bot")
MAX_API_BASE = os.getenv("MAX_API_BASE", "https://platform-api.max.ru")
MAX_SDK_URL = os.getenv("MAX_SDK_URL", "/static/max-sdk.js")
MAX_PARENT_SDK_URL = os.getenv("MAX_PARENT_SDK_URL", "/static/max-parent-sdk.js")
