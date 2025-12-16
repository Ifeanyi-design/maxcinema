import os
from sqlalchemy import create_engine, text

basedir = os.path.abspath(os.path.dirname(__file__))
root_dir = os.path.dirname(basedir)

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # =========================================================
    # 🌐 CANDIDATE DATABASES
    # =========================================================
    
    # 1. Cloud Database (Neon Postgres)
    # ⚠️ PASTE YOUR REAL NEON URL HERE (Make sure it starts with postgresql://)
    CLOUD_DB_URL = os.environ.get("DATABASE_URL")
    
    # 2. Local Database Options
    ROOT_SQLITE = "sqlite:///" + os.path.join(root_dir, "maxcinema.db")
    INSTANCE_SQLITE = "sqlite:///" + os.path.join(root_dir, "instance", "maxcinema.db")
    
    # =========================================================
    # 🧪 THE CONNECTION TEST
    # =========================================================
    
    # Default choice: Assume Cloud works
    final_db_url = CLOUD_DB_URL
    
    # First, check if there is a system override (e.g. on Render/Heroku)
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        final_db_url = env_url
    else:
        # If no system var, TRY to connect to Neon
        try:
            print("☁️  Attempting to connect to Neon Postgres...")
            # We set a short timeout (3 seconds) so your app doesn't freeze if offline
            test_engine = create_engine(CLOUD_DB_URL, connect_args={'connect_timeout': 3})
            
            # Try to run a simple "Hello" query
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("✅ Connection Successful! Using Cloud Database.")
            
        except Exception as e:
            print(f"⚠️  Cloud Connection Failed (Offline?): {e}")
            print("🏠 Switching to Local SQLite Backup...")
            
            # Check which local file actually exists
            if os.path.exists(os.path.join(root_dir, "maxcinema.db")):
                final_db_url = ROOT_SQLITE
                print(f"   -> Found database in ROOT folder.")
            else:
                final_db_url = INSTANCE_SQLITE
                print(f"   -> Found database in INSTANCE folder.")

    # =========================================================
    # 🏁 FINAL ASSIGNMENT
    # =========================================================
    SQLALCHEMY_DATABASE_URI = final_db_url

    # Bytescale / Other Configs...
    BYTESCALE_API_KEY = "secret_W23MTTR8MonEUU4EF5zqMexEmbTJ"
    BYTESCALE_ACCOUNT_ID = "W23MTTR"
    DEFAULT_IMAGE_UPLOAD_URL = "https://image.tmdb.org/t/p/w500"
    BYTESCALE_UPLOAD_URL = f"https://api.bytescale.com/v2/accounts/{BYTESCALE_ACCOUNT_ID}/uploads" if BYTESCALE_ACCOUNT_ID else None