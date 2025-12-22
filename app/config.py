import os
from dotenv import load_dotenv
from sqlalchemy.pool import NullPool  # <--- NEW IMPORT ADDED HERE

load_dotenv()
basedir = os.path.abspath(os.path.dirname(__file__))
root_dir = os.path.dirname(basedir)

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ✅ CONNECTION KEEPER (The "Nuclear" Fix for Neon/Serverless)
    # We use NullPool to force a fresh connection for every request.
    # This prevents the "SSL connection closed" and "Rollback" errors.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,    
        "pool_recycle": 300,      
        "poolclass": NullPool,    # <--- THIS IS THE FIX
    }

    # =========================================================
    # 🚀 INSTANT-BOOT CONFIG (VERSION 2)
    # =========================================================

    CLOUD_DB_URL = os.environ.get("DATABASE_URL")

    # Fix 'channel_binding' crash automatically
    if CLOUD_DB_URL and "channel_binding=require" in CLOUD_DB_URL:
        CLOUD_DB_URL = CLOUD_DB_URL.replace("&channel_binding=require", "").replace("?channel_binding=require", "")

    # Decision Logic: Just assign it. No testing. No waiting.
    if CLOUD_DB_URL:
        SQLALCHEMY_DATABASE_URI = CLOUD_DB_URL
        print("☁️  VERSION 2: INSTANT BOOT LOADING... (Targeting Cloud)")
    else:
        print("🏠 VERSION 2: No Cloud URL found. Using Local SQLite.")
        if os.path.exists(os.path.join(root_dir, "maxcinema.db")):
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(root_dir, "maxcinema.db")
        else:
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(root_dir, "instance", "maxcinema.db")

    # Bytescale / Other Configs...
    BYTESCALE_API_KEY = "secret_W23MTTR8MonEUU4EF5zqMexEmbTJ"
    BYTESCALE_ACCOUNT_ID = "W23MTTR"
    DEFAULT_IMAGE_UPLOAD_URL = "https://image.tmdb.org/t/p/w500"
    BYTESCALE_UPLOAD_URL = f"https://api.bytescale.com/v2/accounts/{BYTESCALE_ACCOUNT_ID}/uploads" if BYTESCALE_ACCOUNT_ID else None
