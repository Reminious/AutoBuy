import os

from dotenv import load_dotenv


load_dotenv(dotenv_path=".env")
MAIL_USER = os.getenv("MAIL_USER")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
if not MAIL_USER or not MAIL_PASSWORD:
    raise ValueError("MAIL_USER and MAIL_PASSWORD must be set in the .env file")

OUTBOX_DIR = os.getenv("OUTBOX_DIR", "outbox")
EMAIL_SCAN_INTERVAL = int(os.getenv("EMAIL_SCAN_INTERVAL", "60"))
STATS_LOG_INTERVAL = int(os.getenv("STATS_LOG_INTERVAL", "30"))
STATS_MILESTONE = int(os.getenv("STATS_MILESTONE", "300"))
