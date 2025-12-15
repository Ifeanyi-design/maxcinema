# app/__init__.py
from .models import User, Genre, AllVideo, Movie, Series, Season, Episode, Comment, Rating, Trailer, StorageServer, RecentItem
import json
from flask import Flask
from .config import Config
from .extensions import db, migrate, login_manager

def create_app(config_class=Config):
    """Application factory for Flask app"""
    
    app = Flask(__name__)
    app.config.from_object(config_class)
    # app.config['SERVER_NAME'] = '192.168.43.141:5000'
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "admin.login"
    login_manager.login_message = "Please log in to access this page."
    
    # Register blueprints
    from .main_routes import main_bp
    app.register_blueprint(main_bp)

    from .admin import admin_bp
    app.register_blueprint(admin_bp)


    app = app
    app.app_context().push()


    return app


