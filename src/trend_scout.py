"""Lightweight market signals for Ukrainian short-form content.

The feed is used only as inspiration. It never replaces fact checking and it
filters sensitive breaking-news topics that are a poor fit for an automated
entertainment channel.
"""

import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from typing import Dict, List

import requests


logger = logging.getLogger(__name__)


class TrendScout:
    """Fetch and cache safe Google Trends RSS topics."""

    _cache: Dict[str, object] = {"expires_at": 0.0, "topics": []}

    def __init__(self):
        self.enabled = os.getenv("ENABLE_MARKET_TRENDS", "True").lower() == "true"
        self.geo = os.getenv("MARKET_GEO", "UA").upper()
        self.timeout = max(2, int(os.getenv("MARKET_TRENDS_TIMEOUT", "8")))
        self.cache_seconds = max(300, int(os.getenv("MARKET_TRENDS_CACHE", "1800")))
        self.url = f"https://trends.google.com/trending/rss?geo={self.geo}"

        blocked = {
            "війна", "обстріл", "ракета", "загинув", "загинула", "смерть",
            "вбивство", "теракт", "аварія", "трагедія", "порно", "казино",
            "ставки", "war", "attack", "killed", "death", "murder",
            "shooting", "crash", "casino", "betting", "porn",
        }
        custom = {
            item.strip().lower()
            for item in os.getenv("TREND_BLOCKLIST", "").split(",")
            if item.strip()
        }
        self.blocked_terms = blocked | custom

    def get_signals(self, niche: Dict, limit: int = 6) -> List[str]:
        """Return a small set of safe, possibly relevant trend titles."""
        evergreen = [
            str(item).strip()
            for item in niche.get("trend_seeds", [])
            if str(item).strip()
        ]
        if not self.enabled:
            return evergreen[:limit]

        topics = self._fetch_topics()
        if not topics:
            return evergreen[:limit]

        keywords = {
            token
            for value in [niche.get("name", ""), *niche.get("keywords", [])]
            for token in self._tokens(str(value))
            if len(token) >= 4
        }

        ranked = []
        for topic in topics:
            topic_tokens = set(self._tokens(topic))
            overlap = len(keywords & topic_tokens)
            ranked.append((overlap, topic))

        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = [topic for _, topic in ranked[: max(2, limit // 2)]]

        result = []
        for signal in selected + evergreen:
            if signal and signal not in result:
                result.append(signal)
        return result[:limit]

    def _fetch_topics(self) -> List[str]:
        now = time.time()
        cached_topics = self._cache.get("topics", [])
        if now < float(self._cache.get("expires_at", 0)) and cached_topics:
            return list(cached_topics)

        try:
            response = requests.get(
                self.url,
                headers={"User-Agent": "Mozilla/5.0 ShortsMarketScout/1.0"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)
            topics = []
            for item in root.findall(".//item"):
                title_node = item.find("title")
                if title_node is None or not title_node.text:
                    continue
                title = self._clean_title(title_node.text)
                if title and self._is_safe(title) and title not in topics:
                    topics.append(title)

            self._cache = {
                "expires_at": now + self.cache_seconds,
                "topics": topics[:30],
            }
            logger.info("Loaded %s safe market signals for %s", len(topics), self.geo)
            return topics[:30]
        except Exception as exc:
            logger.warning("Market trends unavailable; using evergreen ideas: %s", exc)
            self._cache = {"expires_at": now + 300, "topics": []}
            return []

    def _is_safe(self, title: str) -> bool:
        lowered = title.lower()
        return not any(term in lowered for term in self.blocked_terms)

    @staticmethod
    def _clean_title(value: str) -> str:
        value = re.sub(r"\s+", " ", value).strip()
        return value[:120]

    @staticmethod
    def _tokens(value: str) -> List[str]:
        return re.findall(r"[a-zA-Zа-яА-ЯіІїЇєЄґҐ0-9]+", value.lower())
