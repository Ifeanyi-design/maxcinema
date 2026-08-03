web: gunicorn run:app
release: python -c "from app import create_app; from flask_migrate import upgrade; app=create_app(); app.app_context().push(); upgrade()"
