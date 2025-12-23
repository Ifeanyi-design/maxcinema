# app/__init__.py
from .models import User, Genre, AllVideo, Movie, Series, Season, Episode, Comment, Rating, Trailer, StorageServer, RecentItem
import json
import os
from flask import Flask
from .config import Config
from werkzeug.middleware.proxy_fix import ProxyFix
from .extensions import db, migrate, login_manager

# --- THE FIX: Force Flask to use your Domain ---
class ForceHostMiddleware:
    def __init__(self, app, host):
        self.app = app
        self.host = host

    def __call__(self, environ, start_response):
        # We overwrite the Host header so Flask thinks it's always on maxcinema
        environ['HTTP_HOST'] = self.host
        return self.app(environ, start_response)

def create_app(config_class=Config):
    """Application factory for Flask app"""
    
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "admin.login"
    login_manager.login_message = "Please log in to access this page."
    
    # --- PROXY CONFIGURATION ---
    # 1. Standard ProxyFix (Handles http vs https)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # 2. FORCE DOMAIN MIDDLEWARE
    # Only activate this if we are NOT running locally (on your laptop)
    # We check if 'SPACE_ID' exists (Hugging Face always sets this)
    if os.environ.get('SPACE_ID'):
        app.wsgi_app = ForceHostMiddleware(app.wsgi_app, 'maxcinema.name.ng')

    # Register blueprints
    from .main_routes import main_bp
    app.register_blueprint(main_bp)

    from .admin import admin_bp
    app.register_blueprint(admin_bp)

    return app