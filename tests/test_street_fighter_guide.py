import json
import os
import re
import unittest
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-only-secret-for-street-fighter-guide")

from flask import render_template_string, url_for

from app import create_app
from app.extensions import db


class GuideTestConfig:
    TESTING = True
    SECRET_KEY = "test-only-secret-for-street-fighter-guide"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"check_same_thread": False}}
    SITE_BASE_URL = "https://maxcinema.name.ng"
    INDEXNOW_ENABLED = False
    INDEXNOW_KEY = ""
    INDEXNOW_KEY_FILENAME = ""
    INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"


class StreetFighterGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(GuideTestConfig)
        with cls.app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_guide_has_indexable_metadata_and_visible_article_content(self):
        response = self.app.test_client().get(
            "/guides/street-fighter-games-characters-story-legacy"
        )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        canonical = "https://maxcinema.name.ng/guides/street-fighter-games-characters-story-legacy"
        self.assertIn("<h1", html)
        self.assertIn("Street Fighter: Games, Characters, Story, and the Legacy", html)
        self.assertIn(f'<link rel="canonical" href="{canonical}">', html)
        self.assertIn('name="robots" content="index,follow,max-image-preview:large"', html)
        self.assertIn('property="og:type" content="article"', html)
        self.assertIn('src="https://maxcinema.name.ng/static/images/maxcinema-logo.png"', html)
        self.assertIn('content="https://maxcinema.name.ng/static/images/maxcinema-social.png"', html)
        self.assertIn("Browse movies", html)
        self.assertIn("Street Fighter (2026): the current live-action film", html)
        self.assertIn("https://image.tmdb.org/t/p/w600_and_h900_face/pwUb3gdkSrlyMZWs0MFOQg3N5s7.jpg", html)
        self.assertIn("https://www.youtube.com/watch?v=Xt4X4FvXk2A", html)
        self.assertNotIn("https://www.youtube.com/watch?v=R-GU5SymkeM", html)

        with self.app.test_request_context():
            contextual_links = (
                url_for("main.navbar", nav="all_movie", page=1),
                url_for("main.navbar", nav="all_series", page=1),
                url_for("main.trailer"),
                url_for("main.genre", contain="all", genre_type="Action", page=1),
                url_for("main.trending"),
            )
        for internal_url in contextual_links:
            self.assertIn(f'href="{internal_url}"', html)

        schemas = [
            json.loads(block)
            for block in re.findall(
                r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
            )
        ]
        article = next(schema for schema in schemas if schema.get("@type") == "Article")
        breadcrumb = next(schema for schema in schemas if schema.get("@type") == "BreadcrumbList")
        self.assertEqual(article["mainEntityOfPage"]["@id"], canonical)
        self.assertEqual(article["headline"], "Street Fighter Guide: Games, Characters, Story & Legacy")
        self.assertEqual(article["datePublished"], "2026-10-20T00:00:00+01:00")
        self.assertTrue(article["isAccessibleForFree"])
        self.assertEqual(breadcrumb["itemListElement"][-1]["item"], canonical)

    def test_sitemap_lists_the_guide_canonical_url(self):
        response = self.app.test_client().get("/sitemap.xml")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content_type.startswith("application/xml"))
        self.assertIn(
            b"https://maxcinema.name.ng/guides/street-fighter-games-characters-story-legacy",
            response.data,
        )

    def test_robots_allows_crawling_and_advertises_the_sitemap(self):
        response = self.app.test_client().get("/robots.txt")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Allow: /", response.data)
        self.assertIn(b"Sitemap: https://maxcinema.name.ng/sitemap.xml", response.data)

    def test_global_adsterra_script_urls_come_from_environment(self):
        with patch.dict(
            os.environ,
            {
                "AD_POPUNDER_SCRIPT_URL": "https://ads.example.test/popunder.js",
                "AD_SOCIAL_BAR_SCRIPT_URL": "https://ads.example.test/social-bar.js",
            },
        ):
            response = self.app.test_client().get(
                "/guides/street-fighter-games-characters-story-legacy"
            )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn(
            '<script data-cfasync="false" src="https://ads.example.test/popunder.js"></script>',
            html,
        )
        self.assertIn(
            '<script data-cfasync="false" src="https://ads.example.test/social-bar.js"></script>',
            html,
        )

    def test_updated_adsterra_display_and_native_urls_come_from_environment(self):
        with patch.dict(
            os.environ,
            {
                "AD_IFRAME_SCRIPT_URL_TEMPLATE": "https://ads.example.test/22/{key}",
                "AD_BANNER_KEY": "desktop-key",
                "AD_BANNER_MOBILE_KEY": "mobile-key",
                "AD_SIDEBAR_KEY": "sidebar-key",
                "AD_STICKY_DESKTOP_KEY": "sticky-desktop-key",
                "AD_STICKY_MOBILE_KEY": "sticky-mobile-key",
                "AD_NATIVE_SCRIPT_URL": "https://ads.example.test/21/native-key",
                "AD_NATIVE_PLACEMENT_KEY": "native-key",
            },
        ):
            with self.app.test_request_context():
                html = render_template_string(
                    "{{ ads.banner.script_url }}|{{ ads.banner_mobile.script_url }}|"
                    "{{ ads.sidebar.script_url }}|{{ ads.sticky_desktop.script_url }}|"
                    "{{ ads.sticky_mobile.script_url }}|{{ ads.native.script_url }}"
                )

        self.assertEqual(
            html,
            "https://ads.example.test/22/desktop-key|"
            "https://ads.example.test/22/mobile-key|"
            "https://ads.example.test/22/sidebar-key|"
            "https://ads.example.test/22/sticky-desktop-key|"
            "https://ads.example.test/22/sticky-mobile-key|"
            "https://ads.example.test/21/native-key",
        )

    def test_ad_units_do_not_fall_back_to_the_old_adsterra_url_format(self):
        with patch.dict(
            os.environ,
            {
                "AD_IFRAME_SCRIPT_URL_TEMPLATE": "",
                "AD_NATIVE_SCRIPT_URL": "",
                "AD_BANNER_KEY": "desktop-key",
                "AD_NATIVE_PLACEMENT_KEY": "native-key",
            },
        ):
            with self.app.test_request_context():
                html = render_template_string(
                    "{{ ads.banner is none }}|{{ ads.native is none }}"
                )

        self.assertEqual(html, "True|True")


if __name__ == "__main__":
    unittest.main()
