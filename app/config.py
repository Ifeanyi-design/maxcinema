import os
from dotenv import load_dotenv
from sqlalchemy.pool import NullPool

load_dotenv()
basedir = os.path.abspath(os.path.dirname(__file__))
root_dir = os.path.dirname(basedir)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY environment variable is required")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SITE_BASE_URL = (os.environ.get("SITE_BASE_URL") or "https://maxcinema.name.ng").rstrip("/")
    INDEXNOW_ENABLED = (os.environ.get("INDEXNOW_ENABLED") or "1").strip().lower() not in {
        "0", "false", "no", "off"
    }
    INDEXNOW_KEY = (os.environ.get("INDEXNOW_KEY") or "").strip()
    INDEXNOW_KEY_FILENAME = (os.environ.get("INDEXNOW_KEY_FILENAME") or "").strip()
    INDEXNOW_ENDPOINT = (os.environ.get("INDEXNOW_ENDPOINT") or "https://api.indexnow.org/indexnow").strip()

    # =========================================================
    # 🚀 DATABASE CONFIG (DYNAMIC FOR NEON, AZURE, & SQLITE)
    # =========================================================

    CLOUD_DB_URL = os.environ.get("DATABASE_URL")

    if CLOUD_DB_URL:
        # Fix 'channel_binding' crash automatically if present
        if "channel_binding=require" in CLOUD_DB_URL:
            CLOUD_DB_URL = (
                CLOUD_DB_URL
                .replace("&channel_binding=require", "")
                .replace("?channel_binding=require", "")
            )

        SQLALCHEMY_DATABASE_URI = CLOUD_DB_URL
        
        # Smart Check: Detect if the cloud database is Neon
        is_neon = "neon.tech" in CLOUD_DB_URL

        if is_neon:
            # ==============================
            # ☁️ NEON SPECIFIC CONFIG
            # ==============================
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
            print("☁️  DATABASE LAYER: Loaded NEON Config (NullPool Enabled).")
        else:
            # ==============================
            # ⚡ AZURE / PRODUCTION POOL CONFIG
            # ==============================
            SQLALCHEMY_ENGINE_OPTIONS = {
                "pool_size": 10,             # Keep 10 active connections open for speed
                "max_overflow": 20,          # Handle burst traffic up to 30 connections
                "pool_timeout": 30,          # Error out if connection takes >30s
                "pool_recycle": 1800,        # Refresh connections every 30 mins
                "pool_pre_ping": True,       # Check connection health before querying
                "connect_args": {
                    "connect_timeout": 30,
                    "sslmode": "require"     # 🔒 Enforced SSL for Azure security
                },
            }
            print("⚡ DATABASE LAYER: Loaded AZURE Production Config (Connection Pooling Enabled).")

    else:
        # ==============================
        # 🏠 SQLITE CONFIG (LOCAL / HF)
        # ==============================
        print("🏠 DATABASE LAYER: No Cloud URL found. Using Local SQLite.")

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

    # ---- Sports Hub ----
    SPORTS_PROVIDER = os.environ.get("SPORTS_PROVIDER", "thesportsdb")
    SPORTS_TSDB_KEY = os.environ.get("SPORTS_TSDB_KEY", "3")
    SPORTS_TSDB_LEAGUES = os.environ.get("SPORTS_TSDB_LEAGUES")
    SPORTS_APIFOOTBALL_KEY = os.environ.get("SPORTS_APIFOOTBALL_KEY")
    SPORTS_APIFOOTBALL_HOST = os.environ.get("SPORTS_APIFOOTBALL_HOST", "https://v3.football.api-sports.io")

    BYTESCALE_API_KEY = os.environ.get("BYTESCALE_API_KEY", "")
    BYTESCALE_ACCOUNT_ID = os.environ.get("BYTESCALE_ACCOUNT_ID", "")
    DEFAULT_IMAGE_UPLOAD_URL = "https://image.tmdb.org/t/p/w500"
    BYTESCALE_UPLOAD_URL = (
        f"https://api.bytescale.com/v2/accounts/{BYTESCALE_ACCOUNT_ID}/uploads"
        if BYTESCALE_ACCOUNT_ID
        else None
    )
