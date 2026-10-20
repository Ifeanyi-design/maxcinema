import json
import os
import re
import unittest

os.environ.setdefault("SECRET_KEY", "test-only-secret-for-street-fighter-guide")

from flask import url_for

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
        self.assertIn("The screen adaptations are separate interpretations", html)
        self.assertIn("https://www.themoviedb.org/movie/15268-street-fighter-the-legend-of-chun-li", html)

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


if __name__ == "__main__":
    unittest.main()
