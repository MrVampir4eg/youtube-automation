import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.models import Database
from src.free_content_generator import FreeContentGenerator
from src.platform_publishers import UniversalPublisher, build_platform_metadata


class FakeYouTubeUploader:
    def __init__(self, channel_id):
        self.channel_id = channel_id

    def is_configured(self):
        return True

    def upload_video(self, **kwargs):
        return {
            "video_id": self.channel_id,
            "url": f"https://youtube.test/{self.channel_id}",
        }


class ChannelProfilesAffiliateTests(unittest.TestCase):
    def test_offer_is_bound_to_one_channel_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(str(Path(directory) / "test.db"))
            first = db.create_channel_profile("Organic")
            second = db.create_channel_profile("Affiliate")
            offer = db.create_affiliate_offer(second["profile_id"], {
                "name": "Caption AI",
                "url": "https://example.test/?ref=owner",
                "description": "Створює субтитри для коротких відео.",
                "keywords": ["субтитри"],
            })

            self.assertEqual(offer["profile_id"], second["profile_id"])
            self.assertEqual(db.list_affiliate_offers(first["profile_id"]), [])
            self.assertEqual(
                db.list_affiliate_offers(second["profile_id"])[0]["offer_id"],
                offer["offer_id"],
            )

    def test_affiliate_metadata_has_link_and_disclosure(self):
        script = {
            "topic": "Швидкі субтитри",
            "niche": "tech",
            "niche_name": "Tech та AI",
            "hook": "Субтитри більше не треба набирати вручну.",
            "payoff": "Спочатку порівняй результат на одному ролику.",
            "keywords": ["AI", "субтитри"],
        }
        seo = {
            "title": "Швидкі субтитри",
            "description": "Опис\n\n🔗 Caption AI: https://example.test/?ref=owner\nПартнерське посилання.",
            "tags": ["AI"],
            "category_id": "22",
            "affiliate": {
                "name": "Caption AI",
                "url": "https://example.test/?ref=owner",
                "disclosure": "Партнерське посилання.",
            },
        }

        metadata = build_platform_metadata(script, seo)
        self.assertIn("https://example.test/?ref=owner", metadata["youtube"]["description"])
        self.assertIn("Партнерське посилання", metadata["instagram"]["caption"])
        self.assertIn("Партнерське посилання", metadata["tiktok"]["caption"])

    def test_selected_youtube_uploader_is_used(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "video.mp4"
            video.write_bytes(b"fake video")
            default = FakeYouTubeUploader("default-channel")
            selected = FakeYouTubeUploader("selected-channel")
            publisher = UniversalPublisher(default)
            metadata = {
                "youtube": {
                    "title": "Test",
                    "description": "Test",
                    "tags": [],
                    "category_id": "22",
                }
            }
            result = publisher.publish_all(
                video,
                "abc123",
                metadata,
                youtube_uploader=selected,
                platforms=["youtube"],
            )
            self.assertEqual(result["youtube"]["platform_id"], "selected-channel")
            self.assertNotIn("instagram", result)

    def test_fallback_affiliate_script_uses_verified_offer(self):
        with patch.dict(os.environ, {
            "GROQ_API_KEY": "",
            "TOGETHER_API_KEY": "",
            "ENABLE_MARKET_TRENDS": "False",
        }, clear=False):
            generator = FreeContentGenerator()
            niche = generator.niches["tech"]
            offer = {
                "name": "Caption AI",
                "url": "https://example.test/?ref=owner",
                "description": "Створює автоматичні субтитри.",
                "cta": "Посилання — в описі",
            }
            script = generator._generate_fallback(niche, "affiliate", offer)
            self.assertIn("Caption AI", script["full_script"])
            self.assertEqual(script["metadata"]["content_mode"], "affiliate")
            seo = generator.generate_seo_metadata(script)
            self.assertIn(offer["url"], seo["description"])


if __name__ == "__main__":
    unittest.main()
