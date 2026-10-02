import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env():
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
TG_API_ID = int(os.environ.get("TG_API_ID", "0") or 0)
TG_API_HASH = os.environ.get("TG_API_HASH", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo")
DB_PATH = os.environ.get("DB_PATH", str(ROOT / "data" / "crm.db"))
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://127.0.0.1:8013")
# Для тестов: не поднимать бота и userbot
DISABLE_TELEGRAM = os.environ.get("DISABLE_TELEGRAM") == "1"

USERS = {"admin": ("admin", ADMIN_PASSWORD), "demo": ("demo", DEMO_PASSWORD)}
