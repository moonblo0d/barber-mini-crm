"""Налаштування застосунку. Значення беруться з файлу .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
# ID чату (або групи), куди бот надсилає сповіщення про нові заявки.
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0") or 0)
# Пароль до веб-панелі (логін завжди "admin").
PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "admin")
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))
DB_PATH = BASE_DIR / os.getenv("DB_FILE", "crm.sqlite3")
LANDING_DIR = BASE_DIR / "docs"  # docs/ — щоб лендинг можна було віддати через GitHub Pages
PANEL_DIR = BASE_DIR / "panel"

BUSINESS_NAME = os.getenv("BUSINESS_NAME", "BLADE Barber Studio")

SERVICES = [
    "Чоловіча стрижка",
    "Стрижка + борода",
    "Оформлення бороди",
    "Дитяча стрижка",
]

STATUSES = {
    "new": "🆕 Нова",
    "in_progress": "⏳ В роботі",
    "done": "✅ Виконана",
    "rejected": "❌ Відмова",
}
