import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from database.models import Database
from src.policy_guard import MonetizationPolicyGuard, PolicyViolation


def useful_script():
    full = (
        "Ось неочевидний спосіб швидше підготувати коротке відео. "
        "Спочатку сформулюй одну проблему глядача, потім покажи конкретний приклад, "
        "поясни обмеження методу і заверши чесним результатом. Така структура "
        "допомагає утримати увагу без вигаданих обіцянок, спаму або повторення чужого контенту."
    )
    return {
        "hook": "Ось неочевидний спосіб швидше підготувати коротке відео.",
        "body": full,
        "payoff": "Ви отримуєте зрозумілий авторський результат.",
        "cta": "Збережіть приклад.",
        "full_script": full,
    }


class PolicyGuardTests(unittest.TestCase):
    def test_blocks_artificial_engagement_phrase(self):
        with tempfile.TemporaryDirectory() as directory:
            guard = MonetizationPolicyGuard(
                Database(str(Path(directory) / "policy.db"))
            )
            script = useful_script()
            script["cta"] = "Підписка за підписку — пиши в коментарях"
            with self.assertRaises(PolicyViolation):
                guard.validate_script(script, "organic")

    def test_affiliate_requires_https_and_disclosure(self):
        with tempfile.TemporaryDirectory() as directory:
            guard = MonetizationPolicyGuard(
                Database(str(Path(directory) / "policy.db"))
            )
            with self.assertRaises(PolicyViolation):
                guard.validate_script(
                    useful_script(),
                    "affiliate",
                    {"url": "http://example.com", "disclosure": ""},
                )
            guard.validate_script(
                useful_script(),
                "affiliate",
                {
                    "url": "https://example.com/?ref=owner",
                    "disclosure": "Партнерське посилання.",
                },
            )

    def test_automated_frequency_is_capped_per_profile(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"BOT_MAX_DAILY_POSTS_PER_PROFILE": "1"}
        ):
            database = Database(str(Path(directory) / "policy.db"))
            database.add_video({
                "video_id": "abc123",
                "niche": "tech",
                "title": "Test",
                "description": "Test",
                "script": "Test",
                "video_path": "video.mp4",
                "audio_path": "audio.mp3",
                "duration": 30,
                "filesize": 100,
                "ai_cost": 0,
                "profile_id": "default",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            guard = MonetizationPolicyGuard(database)
            with self.assertRaises(PolicyViolation):
                guard.validate_automated_frequency("default")
            database.close()


if __name__ == "__main__":
    unittest.main()
