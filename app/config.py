import os
from dotenv import load_dotenv

load_dotenv()
basedir = os.path.abspath(os.path.dirname(__file__))
root_dir = os.path.dirname(basedir)

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # ✅ THIS IS THE MAGIC PART
    # "pool_pre_ping" checks the connection when a USER visits, not when the app starts.
    # This prevents the 10-second freeze during startup.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,  # Auto-reconnects if Neon is sleeping
        "pool_recycle": 300,
        "pool_size": 10,
        "max_overflow": 20,
    }

    # =========================================================
    # 🚀 INSTANT-BOOT CONFIG
    # =========================================================
    
    # 1. Get Cloud URL
    CLOUD_DB_URL = os.environ.get("DATABASE_URL")
    
    # 2. Clean URL (Fix channel_binding crash)
    if CLOUD_DB_URL and "channel_binding=require" in CLOUD_DB_URL:
        CLOUD_DB_URL = CLOUD_DB_URL.replace("&channel_binding=require", "").replace("?channel_binding=require", "")

    # 3. Decision Logic (No waiting!)
    if CLOUD_DB_URL:
        # Always prefer Cloud. The 'pool_pre_ping' above handles the sleep/wake cycle.
        SQLALCHEMY_DATABASE_URI = CLOUD_DB_URL
        print("☁️  VERSION 2: INSTANT BOOT LOADING...")
        
    else:
        # Fallback only if no Secret is found
        print("🏠 Config: No Cloud URL found. Using Local SQLite.")
        if os.path.exists(os.path.join(root_dir, "maxcinema.db")):
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(root_dir, "maxcinema.db")
        else:
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(root_dir, "instance", "maxcinema.db")

    # Bytescale / Other Configs...
    BYTESCALE_API_KEY = "secret_W23MTTR8MonEUU4EF5zqMexEmbTJ"
    BYTESCALE_ACCOUNT_ID = "W23MTTR"
    DEFAULT_IMAGE_UPLOAD_URL = "https://image.tmdb.org/t/p/w500"
    BYTESCALE_UPLOAD_URL = f"https://api.bytescale.com/v2/accounts/{BYTESCALE_ACCOUNT_ID}/uploads" if BYTESCALE_ACCOUNT_ID else None
    # FORCE UPDATE 1