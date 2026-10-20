import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("SECRET_KEY", "test-only-secret-for-bulk-import")

from app.admin.content import apply_bulk_link_to_episode


class BulkLinkImportTests(unittest.TestCase):
    def test_imported_link_makes_a_coming_soon_episode_available(self):
        episode = SimpleNamespace(
            download_link=None,
            storage_server_id=None,
            coming_soon=True,
        )

        apply_bulk_link_to_episode(episode, "episode-download-code", 12)

        self.assertEqual(episode.download_link, "episode-download-code")
        self.assertEqual(episode.storage_server_id, 12)
        self.assertFalse(episode.coming_soon)

    def test_empty_value_does_not_change_an_episode(self):
        episode = SimpleNamespace(
            download_link=None,
            storage_server_id=None,
            coming_soon=True,
        )

        apply_bulk_link_to_episode(episode, "   ", 12)

        self.assertIsNone(episode.download_link)
        self.assertIsNone(episode.storage_server_id)
        self.assertTrue(episode.coming_soon)


if __name__ == "__main__":
    unittest.main()
