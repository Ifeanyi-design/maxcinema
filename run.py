import os
from app import create_app
from app.models import *  # optional; keep only if your app needs model imports for registration

app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True
    )