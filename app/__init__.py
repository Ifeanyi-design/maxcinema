# app/__init__.py
from .models import (
    User, Genre, AllVideo, Movie, Series, Season, Episode, Comment, Rating,
    Trailer, StorageServer, RecentItem, WatchlistNotify, WeeklyPoll,
    WeeklyPollOption, WeeklyPollVote, SocialVideo, social_video_all_video
)
import json
import os
from flask import Flask, request, has_request_context
from .config import Config
from werkzeug.middleware.proxy_fix import ProxyFix
from .extensions import db, migrate, login_manager
from .seo import default_brand_logo, default_social_image

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
        # Keep ad-layout experiments reversible.  Environment values are strings,
        # so validate the mode here rather than relying on Jinja truthiness.
        ad_configuration = (os.getenv("AD_CONFIGURATION", "legacy") or "legacy").strip().lower()
        if ad_configuration not in {"legacy", "deduped", "optimized"}:
            ad_configuration = "legacy"

        # Smartlink + popunder-observer mode.  ``standard`` is the Adsterra-
        # recommended setup: no custom click handlers opening Smartlinks, no
        # popunder wrappers.  ``optimized`` preserves the previous custom JS
        # (smartlink-trigger handler, probabilistic fallback, popunder cooldown
        # observers) for instant rollback if revenue regresses.
        smartlink_mode = (os.getenv("AD_SMARTLINK_MODE", "standard") or "standard").strip().lower()
        if smartlink_mode not in {"standard", "optimized"}:
            smartlink_mode = "standard"

        def ad_slot_enabled(slot_name, placement_type, is_duplicate=False):
            """Return whether a placement should render in the active layout mode.

            ``legacy`` deliberately returns True for every placement so rollback
            restores the existing layout without changing any Adsterra keys.
            ``deduped`` only suppresses locations explicitly marked as repeated
            uses of the same banner/sidebar code.  ``optimized`` is the later
            manager-requested test: one desktop 728x90 banner, Popunder, and
            Smartlink; Popunder/Smartlink are intentionally not gated here.
            """
            if ad_configuration == "legacy":
                return True
            if ad_configuration == "deduped":
                # Keep one normal banner at the place a visitor is most likely
                # to reach on each type of page.  List/discovery pages retain
                # the global top banner; detail, watch, and download flows keep
                # the existing banner nearest their primary action.
                if placement_type == "banner":
                    endpoint = request.endpoint if has_request_context() else ""
                    primary_banner_by_endpoint = {
                        "main.movie_details": "movie_inline_banner",
                        "main.series_details": "movie_inline_banner",
                        "main.movie_download": "stream_inline_banner",
                        "main.movie_download_page": "dl_inter_server",
                        "main.street_fighter_guide": "article_inline_banner",
                    }
                    return slot_name == primary_banner_by_endpoint.get(endpoint, "top_banner")
                return not is_duplicate
            if placement_type == "banner":
                # Optimized mode: exactly one clean banner placement per page
                # (728x90 on desktop / 320x50 on mobile), placed nearest the
                # user's primary action, plus Popunder and Smartlink.
                endpoint = request.endpoint if has_request_context() else ""
                optimized_banner_by_endpoint = {
                    "main.movie_details": "movie_inline_banner",
                    "main.series_details": "movie_inline_banner",
                    "main.movie_download": "stream_inline_banner",
                    "main.movie_download_page": "dl_inter_server",
                    "main.index": "homepage_mid_banner",
                    "main.featured": "homepage_mid_banner",
                    "main.street_fighter_guide": "article_inline_banner",
                }
                return slot_name == optimized_banner_by_endpoint.get(endpoint, "top_banner")
            return False

        iframe_domain = os.getenv("AD_IFRAME_DOMAIN", "illuminationacceptedkeynote.com")
        iframe_script_url_template = (os.getenv("AD_IFRAME_SCRIPT_URL_TEMPLATE") or "").strip()
        if not (
            iframe_script_url_template.startswith("https://")
            and "{key}" in iframe_script_url_template
        ):
            iframe_script_url_template = None
    
        def iframe_ad(key_env, width, height, fmt="iframe"):
            key = os.getenv(key_env)
            if not key:
                return None
            if iframe_script_url_template:
                script_url = iframe_script_url_template.replace("{key}", key)
            else:
                # Compatibility with the original Adsterra code format.
                script_url = f"https://www.{iframe_domain}/{key}/invoke.js"
            return {
                "key": key,
                "domain": iframe_domain,
                "script_url": script_url,
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

        # Native placements use their own provider domain and placement key.
        # Keep these separate from iframe/banner settings so either format can
        # be updated through deployment configuration without editing templates.
        native_domain = (os.getenv("AD_NATIVE_DOMAIN") or "").strip()
        native_placement_key = (os.getenv("AD_NATIVE_PLACEMENT_KEY") or "").strip()
        native_script_url = (os.getenv("AD_NATIVE_SCRIPT_URL") or "").strip()
        if not native_script_url.startswith("https://"):
            native_script_url = None
        native = None
        if native_placement_key and (native_domain or native_script_url):
            if not native_script_url:
                # Compatibility with the original Adsterra code format.
                native_script_url = (
                    f"https://{native_domain}/{native_placement_key}/invoke.js"
                )
            native = {
                "domain": native_domain,
                "placement_key": native_placement_key,
                "script_url": native_script_url,
            }
    
        # Legacy composed pop URL, retained for the existing body data attribute.
        # It does not control the global Adsterra script units below.
        pop_domain = os.getenv("AD_POP_DOMAIN", "illuminationacceptedkeynote.com")
        pop_path = os.getenv("AD_POP_PATH")
        pop_key = os.getenv("AD_POP_KEY")
    
        pop_url = None
        if pop_path and pop_key:
            pop_url = f"https://www.{pop_domain}/{pop_path}?key={pop_key}"

        def https_script_url(env_name, default_url):
            """Return a deployment-configured HTTPS script URL, or disable it."""
            value = (os.getenv(env_name, default_url) or "").strip()
            return value if value.startswith("https://") else None

        # These are full script URLs copied from Adsterra's active-code page.
        # Defaults preserve the currently deployed units until the Heroku Config
        # Vars are added. Values are rendered into quoted, auto-escaped src
        # attributes in base.html.
        popunder_script_url = https_script_url(
            "AD_POPUNDER_SCRIPT_URL",
            "https://aarems.org/1/597edba21ff8b218fe1a24718d31a80d",
        )
        social_bar_script_url = https_script_url(
            "AD_SOCIAL_BAR_SCRIPT_URL",
            "https://bancadeltempoidea.org/14/81d2132d6afc8317fc42e3a20b663e83",
        )

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
                "native": native,
                "pop_url": pop_url,
                "popunder_script_url": popunder_script_url,
                "social_bar_script_url": social_bar_script_url,
                "smartlink_url": smartlink_url,
                "monetag_inpage_zone": os.getenv("MONETAG_INPAGE_ZONE"),
                "monetag_vignette_zone": os.getenv("MONETAG_VIGNETTE_ZONE"),
                "monetag_push_zone": os.getenv("MONETAG_PUSH_ZONE"),
            },
ad_configuration=ad_configuration,
            ad_slot_enabled=ad_slot_enabled,
            smartlink_mode=smartlink_mode,
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
    def inject_brand_images():
        return {
            "brand_logo_image": default_brand_logo(),
            "brand_social_image": default_social_image(),
        }

    @app.context_processor
    def inject_social_follow_links():
        yt = os.getenv("YOUTUBE_CHANNEL_URL")
        if not yt:
            ch = os.getenv("YOUTUBE_CHANNEL_ID")
            if ch:
                yt = f"https://www.youtube.com/channel/{ch}"
        tt = os.getenv("TIKTOK_URL")
        links = {}
        if yt:
            links["youtube"] = yt
        if tt:
            links["tiktok"] = tt
        return {"follow_links": links}


    # Register blueprints
    from .main_routes import main_bp
    app.register_blueprint(main_bp)
    
    from .admin import admin_bp
    app.register_blueprint(admin_bp)

    from .sports import sports_bp
    app.register_blueprint(sports_bp)

    from .sports.api import api_bp
    app.register_blueprint(api_bp)

    from .sports.cli import sports_cli
    app.cli.add_command(sports_cli)

    # Idempotent repair: add columns the current models have but the live DB
    # is missing (e.g. Heroku Postgres created before a model change). Runs on
    # every boot and must never prevent the app from starting.
    try:
        with app.app_context():
            from .sports.schema_repair import ensure_sports_schema
            ensure_sports_schema()
    except Exception:
        app.logger.exception("Sports schema repair skipped")

    return app
