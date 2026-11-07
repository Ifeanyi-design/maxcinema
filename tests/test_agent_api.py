import hashlib
import os
import unittest
from datetime import date, datetime, timedelta

os.environ.setdefault("SECRET_KEY", "test-only-secret-for-agent-api")

from app import create_app
from app.extensions import db
from app.models import (
    AllVideo,
    AgentAccessToken,
    AgentPairingCode,
    Episode,
    Season,
    Series,
    StorageServer,
    User,
)


class AgentApiTestConfig:
    TESTING = True
    SECRET_KEY = "test-only-secret-for-agent-api"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"check_same_thread": False}}


class AgentApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(AgentApiTestConfig)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()

        now = datetime.utcnow()
        self.user = User(
            username="agent-test-admin",
            email="agent-test@example.test",
            password_hash="not-used",
            is_admin=True,
        )
        db.session.add(self.user)
        db.session.flush()

        self.raw_token = "mca_test-token-for-api"
        self.token = AgentAccessToken(
            token_hash=hashlib.sha256(self.raw_token.encode("utf-8")).hexdigest(),
            label="API test agent",
            scopes=["content:read", "content:write", "links:write"],
            created_by_id=self.user.id,
            created_at=now,
            expires_at=now + timedelta(minutes=60),
        )
        self.server = StorageServer(
            name="Agent Test Telegram",
            server_type="telegram",
            base_url="https://telegram.example.test",
            active=True,
        )
        self.movie = AllVideo(
            name="Agent Test Movie",
            slug="agent-test-movie",
            type="movie",
            active=True,
            released_date=date.today(),
        )
        db.session.add_all([self.token, self.server, self.movie])
        db.session.commit()

        self.client = self.app.test_client()
        self.headers = {"Authorization": f"Bearer {self.raw_token}"}

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_pairing_code_is_single_use_and_token_can_be_revoked(self):
        pairing_code = "single-use-code-for-test"
        now = datetime.utcnow()
        db.session.add(AgentPairingCode(
            code_hash=hashlib.sha256(pairing_code.encode("utf-8")).hexdigest(),
            created_by_id=self.user.id,
            created_at=now,
            expires_at=now + timedelta(minutes=10),
        ))
        db.session.commit()

        response = self.client.post("/api/agent/v1/pair", json={
            "code": pairing_code,
            "label": "Pairing test",
        })
        self.assertEqual(response.status_code, 201)
        issued_token = response.get_json()["access_token"]
        self.assertTrue(issued_token.startswith("mca_"))

        second_use = self.client.post("/api/agent/v1/pair", json={
            "code": pairing_code,
        })
        self.assertEqual(second_use.status_code, 401)

        capabilities = self.client.get(
            "/api/agent/v1/capabilities",
            headers={"Authorization": f"Bearer {issued_token}"},
        )
        self.assertEqual(capabilities.status_code, 200)

        issued_row = AgentAccessToken.query.filter_by(
            token_hash=hashlib.sha256(issued_token.encode("utf-8")).hexdigest()
        ).first()
        issued_row.revoked_at = datetime.utcnow()
        db.session.commit()

        revoked = self.client.get(
            "/api/agent/v1/capabilities",
            headers={"Authorization": f"Bearer {issued_token}"},
        )
        self.assertEqual(revoked.status_code, 401)

    def test_movie_link_preview_apply_and_replacement_confirmation(self):
        preview = self.client.post(
            "/api/agent/v1/links/preview",
            headers=self.headers,
            json={
                "movie_id": self.movie.id,
                "storage_server_id": self.server.id,
                "track": "primary",
                "mode": "fill_missing",
                "code": "initial-download-code",
            },
        )
        self.assertEqual(preview.status_code, 200)
        preview_data = preview.get_json()
        self.assertFalse(preview_data["requires_confirmation"])
        self.assertEqual(preview_data["operation_count"], 1)

        applied = self.client.post(
            "/api/agent/v1/links/apply",
            headers=self.headers,
            json={"preview_token": preview_data["preview_token"]},
        )
        self.assertEqual(applied.status_code, 200)
        db.session.refresh(self.movie)
        self.assertEqual(self.movie.download_link, "initial-download-code")

        replacement_preview = self.client.post(
            "/api/agent/v1/links/preview",
            headers=self.headers,
            json={
                "movie_id": self.movie.id,
                "storage_server_id": self.server.id,
                "track": "primary",
                "mode": "replace",
                "replace_existing": True,
                "code": "replacement-download-code",
            },
        )
        self.assertEqual(replacement_preview.status_code, 200)
        replacement_data = replacement_preview.get_json()
        self.assertTrue(replacement_data["requires_confirmation"])
        self.assertTrue(replacement_data["assignments"][0]["will_replace"])

        blocked = self.client.post(
            "/api/agent/v1/links/apply",
            headers=self.headers,
            json={"preview_token": replacement_data["preview_token"]},
        )
        self.assertEqual(blocked.status_code, 409)

        approved = self.client.post(
            "/api/agent/v1/links/apply",
            headers=self.headers,
            json={
                "preview_token": replacement_data["preview_token"],
                "confirm_replacements": True,
            },
        )
        self.assertEqual(approved.status_code, 200)
        db.session.refresh(self.movie)
        self.assertEqual(self.movie.download_link, "replacement-download-code")

    def test_future_episode_is_not_linkable_even_when_named_in_assignment(self):
        today_lagos = (datetime.utcnow() + timedelta(hours=1)).date()
        series_video = AllVideo(
            name="Agent Test Series",
            slug="agent-test-series",
            type="series",
            active=True,
        )
        db.session.add(series_video)
        db.session.flush()
        series = Series(all_video_id=series_video.id, num_seasons=1, num_episodes=2)
        db.session.add(series)
        db.session.flush()
        season = Season(series_id=series.id, season_number=1, num_episodes=2)
        db.session.add(season)
        db.session.flush()
        released = Episode(
            season_id=season.id,
            episode_number=1,
            name="Released",
            released_date=today_lagos,
        )
        future = Episode(
            season_id=season.id,
            episode_number=2,
            name="Not Yet Released",
            released_date=today_lagos + timedelta(days=5),
            coming_soon=True,
        )
        db.session.add_all([released, future])
        db.session.commit()

        preview = self.client.post(
            "/api/agent/v1/links/preview",
            headers=self.headers,
            json={
                "series_id": series_video.id,
                "season_number": 1,
                "storage_server_id": self.server.id,
                "track": "primary",
                "mode": "fill_missing",
                "assignments": [
                    {"episode_number": 1, "code": "released-episode-code"},
                    {"episode_number": 2, "code": "future-episode-code"},
                ],
            },
        )
        self.assertEqual(preview.status_code, 200)
        data = preview.get_json()
        self.assertEqual(data["operation_count"], 1)
        self.assertEqual(data["skipped"][0]["episode_number"], 2)

        applied = self.client.post(
            "/api/agent/v1/links/apply",
            headers=self.headers,
            json={"preview_token": data["preview_token"]},
        )
        self.assertEqual(applied.status_code, 200)
        db.session.refresh(released)
        db.session.refresh(future)
        self.assertEqual(released.download_link, "released-episode-code")
        self.assertIsNone(future.download_link)
        self.assertTrue(future.coming_soon)


if __name__ == "__main__":
    unittest.main()
