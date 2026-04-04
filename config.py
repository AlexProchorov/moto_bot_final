import os
from pathlib import Path
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Директории
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Bot
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in .env")

# Admins
ADMIN_IDS = []
_raw_admins = os.getenv("ADMIN_IDS", "").strip()
if _raw_admins:
    for x in _raw_admins.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.append(int(x))
if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS must be set in .env (comma-separated numeric IDs)")

# Group
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0").strip() or "0")
if not GROUP_CHAT_ID:
    raise ValueError("GROUP_CHAT_ID must be set in .env")

# Database
DB_PATH = DATA_DIR / "database.db"
DB_URL = f"sqlite:///{DB_PATH}"

# Other

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
MOTORCYCLES_FILE = Path(__file__).resolve().parent.parent / "data" / "motorcycles.json"
MOTO_MAPPING_PATH = str(DATA_DIR / "moto_mapping.json")

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
WEATHER_CITY = os.getenv("WEATHER_CITY", "Moscow")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")