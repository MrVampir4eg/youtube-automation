import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.models import Database
from src.platform_publishers import (
    FacebookPublisher,
    InstagramPublisher,
    PublishResult,
    TikTokPublisher,
    UniversalPublisher,
    build_platform_metadata,
    is_valid_media_signature,
    media_share_signature,
)


class FakeResponse:
    def __init__(self, payload=None, ok=True, text=""):
        self.payload = payload or {}
        self.ok = ok
        self.text = text

    def json(self):
        return self.payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(self.text or "HTTP error")


class TikTokSession:
    def __init__(self):
        self.posts = []
        self.puts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return FakeResponse({
            "data": {"publish_id": "pub-1", "upload_url": "https://upload.test/1"},
            "error": {"code": "ok", "message": ""},
        })

    def put(self, url, **kwargs):
        self.puts.append((url, kwargs))
        return FakeResponse()


class InstagramSession:
    def __init__(self):
        self.posts = []
        self.gets = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if url.endswith('/media_publish'):
            return FakeResponse({"id": "ig-media-1"})
        return FakeResponse({"id": "ig-container-1"})

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        fields = kwargs.get("params", {}).get("fields")
        if fields == "status_code,status":
            return FakeResponse({"status_code": "FINISHED"})
        return FakeResponse({"permalink": "https://instagram.test/reel/1"})


class FacebookSession:
    def __init__(self):
        self.posts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        data = kwargs.get("data")
        if isinstance(data, dict) and data.get("upload_phase") == "start":
            return FakeResponse({
                "video_id": "fb-reel-1",
                "upload_url": "https://facebook-upload.test/1",
            })
        if url == "https://facebook-upload.test/1":
            return FakeResponse({"success": True})
        return FakeResponse({"success": True})

    def get(self, url, **kwargs):
        return FakeResponse({"permalink_url": "https://facebook.test/reel/1"})


class FakeYouTube:
    def is_configured(self):
        return True

    def upload_video(self, **kwargs):
        return {"video_id": "yt-1", "url": "https://youtube.test/yt-1"}


class SuccessfulAdapter:
    def __init__(self, platform):
        self.platform = platform

    def publish(self, *args, **kwargs):
        return PublishResult(
            self.platform,
            "published",
            "ok",
            f"{self.platform}-1",
            f"https://{self.platform}.test/1",
        )


class FailingAdapter:
    def publish(self, *args, **kwargs):
        raise RuntimeError("expected isolated failure")


class PlatformPublisherTests(unittest.TestCase):
    def test_metadata_is_platform_specific_and_within_limits(self):
        script = {
            "niche": "fun_facts",
            "niche_name": "Дивні факти",
            "topic": "Восьминіг",
            "hook": "Ось чому восьминіг ходить, а не пливе.",
            "payoff": "Так він витрачає менше енергії.",
            "keywords": ["наука", "тварини"],
        }
        seo = {
            "title": "Чому восьминіг ходить",
            "description": "Коротке пояснення",
            "tags": ["shorts", "наука"],
            "category_id": "22",
        }
        result = build_platform_metadata(script, seo)
        self.assertEqual(set(result), {"youtube", "instagram", "tiktok", "facebook"})
        self.assertLessEqual(len(result["youtube"]["title"]), 100)
        self.assertLessEqual(len(result["instagram"]["caption"]), 2200)
        self.assertNotEqual(result["instagram"]["caption"], result["tiktok"]["caption"])
        self.assertIn("#Shorts", result["youtube"]["description"])

    def test_media_signature_rejects_wrong_video(self):
        with patch.dict(os.environ, {"MEDIA_SHARE_SECRET": "unit-secret"}):
            signature = media_share_signature("abc123")
            self.assertTrue(is_valid_media_signature("abc123", signature))
            self.assertFalse(is_valid_media_signature("other", signature))

    def test_tiktok_inbox_upload_uses_official_two_step_flow(self):
        session = TikTokSession()
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"TIKTOK_ACCESS_TOKEN": "token", "TIKTOK_POST_MODE": "inbox"},
        ):
            path = Path(directory) / "video.mp4"
            path.write_bytes(b"video-bytes")
            publisher = TikTokPublisher(session=session)
            result = publisher.publish(path, {"caption": "Test"}, "abc123")

        self.assertEqual(result.status, "awaiting_user")
        self.assertIn("/publish/inbox/video/init/", session.posts[0][0])
        self.assertEqual(session.puts[0][1]["headers"]["Content-Type"], "video/mp4")

    def test_instagram_creates_polls_and_publishes_reel(self):
        session = InstagramSession()
        variables = {
            "INSTAGRAM_ACCESS_TOKEN": "token",
            "INSTAGRAM_USER_ID": "123",
            "PUBLIC_BASE_URL": "https://render.test",
            "MEDIA_SHARE_SECRET": "secret",
        }
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, variables):
            path = Path(directory) / "video.mp4"
            path.write_bytes(b"video")
            publisher = InstagramPublisher(session=session)
            result = publisher.publish(path, {"caption": "Caption"}, "abc123")

        self.assertEqual(result.status, "published")
        self.assertEqual(result.url, "https://instagram.test/reel/1")
        self.assertIn("/123/media", session.posts[0][0])
        self.assertIn("/api/media/abc123/", session.posts[0][1]["data"]["video_url"])

    def test_facebook_uses_reels_start_upload_finish_flow(self):
        session = FacebookSession()
        variables = {
            "FACEBOOK_PAGE_ACCESS_TOKEN": "token",
            "FACEBOOK_PAGE_ID": "456",
        }
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, variables):
            path = Path(directory) / "video.mp4"
            path.write_bytes(b"video")
            publisher = FacebookPublisher(session=session)
            result = publisher.publish(path, {"description": "Description"}, "abc123")

        self.assertEqual(result.status, "published")
        self.assertEqual(result.url, "https://facebook.test/reel/1")
        self.assertEqual(session.posts[0][1]["data"]["upload_phase"], "start")
        self.assertEqual(session.posts[-1][1]["data"]["upload_phase"], "finish")

    def test_one_platform_failure_does_not_stop_others(self):
        metadata = {
            "youtube": {
                "title": "Title",
                "description": "Description",
                "tags": [],
                "category_id": "22",
            },
            "tiktok": {"caption": "Caption"},
            "instagram": {"caption": "Caption"},
            "facebook": {"description": "Description"},
        }
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"AUTO_PUBLISH_PLATFORMS": "youtube,tiktok,instagram"},
        ):
            path = Path(directory) / "video.mp4"
            path.write_bytes(b"video")
            publisher = UniversalPublisher(FakeYouTube())
            publisher.tiktok = FailingAdapter()
            publisher.instagram = SuccessfulAdapter("instagram")
            with patch("src.platform_publishers.logger.exception"):
                results = publisher.publish_all(path, "abc123", metadata)

        self.assertEqual(results["youtube"]["status"], "published")
        self.assertEqual(results["tiktok"]["status"], "failed")
        self.assertEqual(results["instagram"]["status"], "published")

    def test_database_round_trips_platform_results(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(str(Path(directory) / "test.db"))
            database.add_video({
                "video_id": "abc123",
                "niche": "fun_facts",
                "title": "Test",
                "description": "Test",
                "script": "Test",
                "video_path": "video.mp4",
                "audio_path": "audio.mp3",
                "duration": 20,
                "filesize": 100,
                "youtube_video_id": None,
                "youtube_url": None,
                "platform_results": {
                    "instagram": {"status": "published", "url": "https://example.test"}
                },
                "ai_cost": 0,
                "created_at": "2026-07-22T00:00:00",
            })
            stored = database.get_video("abc123")
            database.close()

        self.assertEqual(stored["platform_results"]["instagram"]["status"], "published")

    def test_database_migrates_existing_v11_table(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            connection = sqlite3.connect(path)
            connection.execute(
                "CREATE TABLE videos (id INTEGER PRIMARY KEY, video_id TEXT UNIQUE NOT NULL, "
                "niche TEXT NOT NULL, title TEXT NOT NULL, description TEXT, script TEXT, "
                "video_path TEXT, audio_path TEXT, duration REAL, filesize INTEGER, "
                "youtube_video_id TEXT, youtube_url TEXT, ai_cost REAL DEFAULT 0, "
                "created_at TEXT NOT NULL, updated_at TEXT)"
            )
            connection.commit()
            connection.close()

            database = Database(str(path))
            columns = {
                row["name"]
                for row in database.conn.execute("PRAGMA table_info(videos)").fetchall()
            }
            database.close()

        self.assertIn("platform_results", columns)


if __name__ == "__main__":
    unittest.main()
