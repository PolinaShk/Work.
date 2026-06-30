import os
from dotenv import load_dotenv
import random

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID")) if os.getenv("ADMIN_CHAT_ID") else None
LOGS_CHAT_ID = int(os.getenv("LOGS_CHAT_ID")) if os.getenv("LOGS_CHAT_ID") else None

PROXY_LIST = os.getenv("PROXY_LIST", "")
PROXY_URL = os.getenv("PROXY_URL") or None

# Если есть PROXY_LIST, выбираем случайный
if PROXY_LIST and not PROXY_URL:
    proxies = [p.strip() for p in PROXY_LIST.split(",") if p.strip()]
    if proxies:
        PROXY_URL = random.choice(proxies)

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT")) if os.getenv("DB_PORT") else None
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_SOCKET = os.getenv("DB_SOCKET")

if DB_SOCKET:
    DATABASE_URL = f"mysql+aiomysql://{DB_USER}:{DB_PASSWORD}@localhost/{DB_NAME}?unix_socket={DB_SOCKET}"
else:
    DATABASE_URL = f"mysql+aiomysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

ZOOM_ACCOUNT_ID = os.getenv("ZOOM_ACCOUNT_ID")
ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET")

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.yandex.ru")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")