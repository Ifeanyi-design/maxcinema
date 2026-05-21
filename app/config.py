import os
from dotenv import load_dotenv
from sqlalchemy.pool import NullPool

load_dotenv()
basedir = os.path.abspath(os.path.dirname(__file__))
root_dir = os.path.dirname(basedir)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SITE_BASE_URL = (os.environ.get("SITE_BASE_URL") or "https://maxcinema.name.ng").rstrip("/")
    INDEXNOW_ENABLED = (os.environ.get("INDEXNOW_ENABLED") or "1").strip().lower() not in {
        "0", "false", "no", "off"
    }
    INDEXNOW_KEY = (os.environ.get("INDEXNOW_KEY") or "").strip()
    INDEXNOW_KEY_FILENAME = (os.environ.get("INDEXNOW_KEY_FILENAME") or "").strip()
    INDEXNOW_ENDPOINT = (os.environ.get("INDEXNOW_ENDPOINT") or "https://api.indexnow.org/indexnow").strip()

    # =========================================================
    # 🚀 DATABASE CONFIG (SAFE FOR NEON + SQLITE)
    # =========================================================

    CLOUD_DB_URL = os.environ.get("DATABASE_URL")

    # Fix 'channel_binding' crash automatically (Neon)
    if CLOUD_DB_URL and "channel_binding=require" in CLOUD_DB_URL:
        CLOUD_DB_URL = (
            CLOUD_DB_URL
            .replace("&channel_binding=require", "")
            .replace("?channel_binding=require", "")
        )

    if CLOUD_DB_URL:
        # ==============================
        # ☁️ NEON / POSTGRES CONFIG
        # ==============================
        SQLALCHEMY_DATABASE_URI = CLOUD_DB_URL
        SQLALCHEMY_ENGINE_OPTIONS = {
            "poolclass": NullPool,     # Force fresh connection (Neon-safe)
            "pool_pre_ping": True,
            "connect_args": {
                "connect_timeout": 60,  # Allow Neon to wake up
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
            },
        }
        print("☁️  VERSION 2: INSTANT BOOT LOADING... (Targeting Cloud)")

    else:
        # ==============================
        # 🏠 SQLITE CONFIG (LOCAL / HF)
        # ==============================
        print("🏠 VERSION 2: No Cloud URL found. Using Local SQLite.")

        if os.path.exists(os.path.join(root_dir, "maxcinema.db")):
            SQLALCHEMY_DATABASE_URI = (
                "sqlite:///" + os.path.join(root_dir, "maxcinema.db")
            )
        else:
            SQLALCHEMY_DATABASE_URI = (
                "sqlite:///" + os.path.join(root_dir, "instance", "maxcinema.db")
            )

        # IMPORTANT: SQLite-safe engine options ONLY
        SQLALCHEMY_ENGINE_OPTIONS = {
            "connect_args": {
                "check_same_thread": False
            }
        }

    # =========================================================
    # OTHER CONFIGS
    # =========================================================

    BYTESCALE_API_KEY = "secret_W23MTTR8MonEUU4EF5zqMexEmbTJ"
    BYTESCALE_ACCOUNT_ID = "W23MTTR"
    DEFAULT_IMAGE_UPLOAD_URL = "https://image.tmdb.org/t/p/w500"
    BYTESCALE_UPLOAD_URL = (
        f"https://api.bytescale.com/v2/accounts/{BYTESCALE_ACCOUNT_ID}/uploads"
        if BYTESCALE_ACCOUNT_ID
        else None
    )
