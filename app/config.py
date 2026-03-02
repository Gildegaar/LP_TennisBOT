import os

def get_env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)

BOT_TOKEN = get_env("BOT_TOKEN")          # può essere None, lo validiamo in main
DATABASE_URL = get_env("DATABASE_URL")    # idem
BASE_URL = get_env("BASE_URL", "")
ADMIN_ID = int(get_env("ADMIN_ID", "201907795") or "201907795")
TZ = get_env("TZ", "Europe/Rome")
WEBHOOK_PATH = "/webhook"