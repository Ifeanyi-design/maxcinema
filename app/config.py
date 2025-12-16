import os
from sqlalchemy import create_engine, text

basedir = os.path.abspath(os.path.dirname(__file__))
root_dir = os.path.dirname(basedir)

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,  # Checks if connection is alive before using it
        "pool_recycle": 300,    # Refreshes connections every 5 minutes
    }

    # =========================================================
    # 🧠 INTELLIGENT DATABASE SWITCHER
    # =========================================================
    
    # 1. Get the Cloud URL (from .env or Hugging Face Secrets)
    CLOUD_DB_URL = "postgresql://neondb_owner:npg_GjPbLC7T9rtZ@ep-withered-shadow-a4a0d1w6-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    
    # 2. Define Local Options
    ROOT_SQLITE = "sqlite:///" + os.path.join(root_dir, "maxcinema.db")
    INSTANCE_SQLITE = "sqlite:///" + os.path.join(root_dir, "instance", "maxcinema.db")

    # 3. Decision Logic
    final_db_url = None

    # STEP A: If a Cloud URL exists, TEST IT.
    if CLOUD_DB_URL:
        try:
            print("☁️  Testing connection to Neon Postgres...")
            # Set a 3-second timeout so it doesn't freeze if you are offline
            test_engine = create_engine(CLOUD_DB_URL, connect_args={'connect_timeout': 3})
            
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            print("✅ Connection Successful! Using Cloud Database.")
            final_db_url = CLOUD_DB_URL
            
        except Exception as e:
            print(f"⚠️  Cloud Connection Failed (Offline?): {e}")
            print("   -> Dropping to backup mode.")
            final_db_url = None  # Force fallback to SQLite

    # STEP B: If Cloud is missing OR failed the test, use Local SQLite
    if not final_db_url:
        print("🏠 Switching to Local SQLite Backup...")
        # Check which file actually exists on your disk
        if os.path.exists(os.path.join(root_dir, "maxcinema.db")):
            final_db_url = ROOT_SQLITE
            print("   -> Found database in ROOT folder.")
        else:
            final_db_url = INSTANCE_SQLITE
            print("   -> Found database in INSTANCE folder.")

    # =========================================================
    # 🏁 FINAL ASSIGNMENT
    # =========================================================
    SQLALCHEMY_DATABASE_URI = final_db_url

    # Bytescale / Other Configs...
    BYTESCALE_API_KEY = "secret_W23MTTR8MonEUU4EF5zqMexEmbTJ"
    BYTESCALE_ACCOUNT_ID = "W23MTTR"
    DEFAULT_IMAGE_UPLOAD_URL = "https://image.tmdb.org/t/p/w500"
    BYTESCALE_UPLOAD_URL = f"https://api.bytescale.com/v2/accounts/{BYTESCALE_ACCOUNT_ID}/uploads" if BYTESCALE_ACCOUNT_ID else None
