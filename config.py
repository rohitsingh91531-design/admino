import os
from datetime import timedelta

BOT_TOKEN = os.environ.get("BOT_TOKEN", "7999145702:AAGv3Gz8WO28iiCM-UQ6WZE6k92RZ3qsZlg")
API_ID = int(os.environ.get("API_ID", "21447993"))
API_HASH = os.environ.get("API_HASH", "2b0787826e6c3f429bf8db86f940531f")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://admino_bot:Rs179988@admino.dasrdsn.mongodb.net/?retryWrites=true&w=majority&appName=admino")
DB_NAME = os.environ.get("DB_NAME", "admino_db")

LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "-1003083351452"))
UPDATE_CHANNEL = int(os.environ.get("UPDATE_CHANNEL", "-1003135547865"))

ADMIN_ID = int(os.environ.get("ADMIN_ID", "6268090266"))

SHORTENER_API = os.environ.get("SHORTENER_API", "")  # optional
AUTO_DELETE_HOURS = int(os.environ.get("AUTO_DELETE_HOURS", "24"))

# How often sweeper runs (in seconds)
SWEEPER_INTERVAL = int(os.environ.get("SWEEPER_INTERVAL", "3600"))

# deep link prefix format: https://t.me/<BOT_USERNAME>?start=file_<id>
BOT_USERNAME = os.environ.get("BOT_USERNAME", "hncjfuvbot")
