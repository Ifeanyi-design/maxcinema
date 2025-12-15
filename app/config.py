import os

basedir = os.path.abspath(os.path.dirname(__file__))
root_dir = os.path.dirname(basedir)

class Config:
    # Updated DB path to match the root location
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "sqlite:///" + os.path.join(root_dir, "maxcinema.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")
    # Bytescale
    BYTESCALE_API_KEY = "secret_W23MTTR8MonEUU4EF5zqMexEmbTJ"
    BYTESCALE_ACCOUNT_ID = "W23MTTR"
    DEFAULT_IMAGE_UPLOAD_URL = "https://image.tmdb.org/t/p/w500"
    BYTESCALE_UPLOAD_URL = f"https://api.bytescale.com/v2/accounts/{BYTESCALE_ACCOUNT_ID}/uploads" if BYTESCALE_ACCOUNT_ID else None