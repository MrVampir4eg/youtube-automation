"""Conservative pre-publish checks for monetization-safe automation."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from urllib.parse import urlparse

from database.models import Database


class PolicyViolation(ValueError):
    pass


class MonetizationPolicyGuard:
    """Stops obvious spam/compliance mistakes; it cannot guarantee monetization."""

    BLOCKED_PHRASES = (
        "sub4sub",
        "підписка за підписку",
        "купи перегляди",
        "накрутка переглядів",
        "гарантований заробіток",
        "100% прибуток",
        "без ризику заробиш",
        "тисни на рекламу",
    )

    def __init__(self, db: Database):
        self.db = db
        try:
            configured_limit = int(
                os.getenv("BOT_MAX_DAILY_POSTS_PER_PROFILE", "3")
            )
        except ValueError:
            configured_limit = 3
        self.max_automated_daily = max(
            1, min(8, configured_limit)
        )

    def validate_script(
        self,
        script: Dict,
        content_mode: str,
        affiliate_offer: Optional[Dict] = None,
    ) -> None:
        text = " ".join(
            str(script.get(key) or "")
            for key in ("hook", "body", "payoff", "cta", "full_script")
        ).lower()
        matched = next((phrase for phrase in self.BLOCKED_PHRASES if phrase in text), None)
        if matched:
            raise PolicyViolation(f"Policy Guard зупинив заборонену фразу: {matched}")
        if len(script.get("full_script", "").split()) < 30:
            raise PolicyViolation("Сценарій надто короткий для оригінального корисного ролика")
        if not script.get("hook") or not script.get("body"):
            raise PolicyViolation("Сценарій не має повної авторської структури")

        if content_mode == "affiliate":
            if not affiliate_offer:
                raise PolicyViolation("Партнерська пропозиція не вибрана")
            parsed = urlparse(str(affiliate_offer.get("url") or ""))
            if parsed.scheme != "https" or not parsed.netloc:
                raise PolicyViolation("Партнерське посилання повинно використовувати HTTPS")
            if not str(affiliate_offer.get("disclosure") or "").strip():
                raise PolicyViolation("Для партнерського ролика потрібна позначка про комісію")

    def validate_metadata(self, seo: Dict, content_mode: str) -> None:
        description = str(seo.get("description") or "")
        if content_mode == "affiliate":
            affiliate = seo.get("affiliate") or {}
            for required in (affiliate.get("url"), affiliate.get("disclosure")):
                if not required or str(required) not in description:
                    raise PolicyViolation(
                        "Публікацію зупинено: у описі немає посилання або disclosure"
                    )

    def validate_automated_frequency(self, profile_id: str) -> None:
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        count = self.db.count_videos_since(profile_id, since)
        if count >= self.max_automated_daily:
            raise PolicyViolation(
                f"Добовий ліміт бота для каналу: {self.max_automated_daily} ролики"
            )
