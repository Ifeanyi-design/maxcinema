# app/__init__.py
from .models import (
    User, Genre, AllVideo, Movie, Series, Season, Episode, Comment, Rating,
    Trailer, StorageServer, RecentItem, WatchlistNotify, WeeklyPoll,
    WeeklyPollOption, WeeklyPollVote
)
import json
import os
from flask import Flask, request, has_request_context
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


    @app.context_processor
    def inject_ads():
        iframe_domain = os.getenv("AD_IFRAME_DOMAIN", "illuminationacceptedkeynote.com")
    
        def iframe_ad(key_env, width, height, fmt="iframe"):
            key = os.getenv(key_env)
            if not key:
                return None
            return {
                "key": key,
                "domain": iframe_domain,
                "format": fmt,
                "width": width,
                "height": height,
            }
    
        # IFRAME ADS
        banner = iframe_ad("AD_BANNER_KEY", 728, 90)
        banner_mobile = iframe_ad("AD_BANNER_MOBILE_KEY", 320, 50)
        sidebar = iframe_ad("AD_SIDEBAR_KEY", 300, 250)
        sticky_desktop = iframe_ad("AD_STICKY_DESKTOP_KEY", 728, 90)
        sticky_mobile = iframe_ad("AD_STICKY_MOBILE_KEY", 320, 50)
    
        # POPUNDER URL (built server-side from secrets)
        pop_domain = os.getenv("AD_POP_DOMAIN", "illuminationacceptedkeynote.com")
        pop_path = os.getenv("AD_POP_PATH")
        pop_key = os.getenv("AD_POP_KEY")
    
        pop_url = None
        if pop_path and pop_key:
            pop_url = f"https://www.{pop_domain}/{pop_path}?key={pop_key}"

        # SMARTLINK — completely separate monetization channel
        # Set AD_SMARTLINK_URL directly in .env, or build from parts
        smartlink_url = os.getenv("AD_SMARTLINK_URL")
        if not smartlink_url:
            sl_domain = os.getenv("AD_SMARTLINK_DOMAIN", "")
            sl_path   = os.getenv("AD_SMARTLINK_PATH", "")
            if sl_domain and sl_path:
                smartlink_url = f"https://{sl_domain}/{sl_path}"
    
        return dict(
            ads={
                "banner": banner,
                "banner_mobile": banner_mobile,
                "sidebar": sidebar,
                "sticky_desktop": sticky_desktop,
                "sticky_mobile": sticky_mobile,
                "pop_url": pop_url,
                "smartlink_url": smartlink_url,
                "monetag_inpage_zone": os.getenv("MONETAG_INPAGE_ZONE"),
                "monetag_vignette_zone": os.getenv("MONETAG_VIGNETTE_ZONE"),
                "monetag_push_zone": os.getenv("MONETAG_PUSH_ZONE"),
            }
        )

    def get_country_code() -> str:
        # Background threads (release notifications, etc.) have an app context
        # but no request context; guard so render_template can't crash on `request`.
        if not has_request_context():
            return "XX"

        # Cloudflare header (best)
        cc = request.headers.get("CF-IPCountry")
        if cc and len(cc) == 2:
            return cc.upper()

        # Fallbacks (in case Vercel/middlewares rename it later)
        cc = request.headers.get("X-Country") or request.headers.get("X-Vercel-IP-Country")
        if cc and len(cc) == 2:
            return cc.upper()

        return "XX"

    @app.context_processor
    def inject_country():
        return {"country": get_country_code()}

    @app.context_processor
    def inject_telegram_links():
        main_group_url = os.getenv("TELEGRAM_MAIN_GROUP_URL", "https://t.me/MaxCinemaOfficial").strip()
        notify_group_url = os.getenv("TELEGRAM_NOTIFY_GROUP_URL", main_group_url).strip()
        return {
            "telegram_main_group_url": main_group_url,
            "telegram_notify_group_url": notify_group_url,
        }
    

    # Register blueprints
    from .main_routes import main_bp
    app.register_blueprint(main_bp)
    
    from .admin import admin_bp
    app.register_blueprint(admin_bp)

    from .sports import sports_bp
    app.register_blueprint(sports_bp)

    from .sports.cli import sports_cli
    app.cli.add_command(sports_cli)

    return app
