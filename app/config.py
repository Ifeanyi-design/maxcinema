import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
basedir = os.path.abspath(os.path.dirname(__file__))
root_dir = os.path.dirname(basedir)

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # =========================================================
    # 🧠 INTELLIGENT DATABASE SWITCHER (WITH BACKUP)
    # =========================================================
    
    # 1. Get the Cloud URL
    CLOUD_DB_URL = os.environ.get("DATABASE_URL")
    
    # 2. Clean URL (Fix channel_binding crash)
    if CLOUD_DB_URL and "channel_binding=require" in CLOUD_DB_URL:
        CLOUD_DB_URL = CLOUD_DB_URL.replace("&channel_binding=require", "").replace("?channel_binding=require", "")

    # 3. Define Local Backup Path
    if os.path.exists(os.path.join(root_dir, "maxcinema.db")):
        LOCAL_BACKUP = "sqlite:///" + os.path.join(root_dir, "maxcinema.db")
    else:
        LOCAL_BACKUP = "sqlite:///" + os.path.join(root_dir, "instance", "maxcinema.db")

    # 4. DECISION LOGIC
    # We default to the Backup, then try to upgrade to Cloud.
    active_db_url = LOCAL_BACKUP
    
    if CLOUD_DB_URL:
        try:
            print("☁️  Attempting to connect to Neon (Waiting up to 10s)...")
            
            # Create a temporary engine just to test the connection
            # We wait 10 seconds to allow Neon to wake up from sleep.
            test_engine = create_engine(CLOUD_DB_URL, connect_args={'connect_timeout': 10})
            
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            print("✅ Neon is Awake & Working! Switching to Cloud.")
            active_db_url = CLOUD_DB_URL
            
        except Exception as e:
            print(f"⚠️  Neon Connection Failed: {e}")
            print("🛑 CLOUD IS DOWN. REMAINING ON LOCAL BACKUP.")
            # active_db_url stays as LOCAL_BACKUP

    # =========================================================
    # 🏁 FINAL ASSIGNMENT
    # =========================================================
    SQLALCHEMY_DATABASE_URI = active_db_url
    print(f"🚀 Database Configured: {'NEON CLOUD' if active_db_url == CLOUD_DB_URL else 'LOCAL SQLITE BACKUP'}")

    # Bytescale / Other Configs...
    BYTESCALE_API_KEY = "secret_W23MTTR8MonEUU4EF5zqMexEmbTJ"
    BYTESCALE_ACCOUNT_ID = "W23MTTR"
    DEFAULT_IMAGE_UPLOAD_URL = "https://image.tmdb.org/t/p/w500"
    BYTESCALE_UPLOAD_URL = f"https://api.bytescale.com/v2/accounts/{BYTESCALE_ACCOUNT_ID}/uploads" if BYTESCALE_ACCOUNT_ID else None