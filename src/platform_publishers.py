"""Official multi-platform publishing adapters for vertical videos.

The module keeps every destination optional. A missing or rejected credential
must never prevent the rendered MP4 from being saved or another platform from
publishing successfully.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

import requests


logger = logging.getLogger(__name__)

META_GRAPH_VERSION = os.getenv("META_GRAPH_API_VERSION", "v25.0")
META_GRAPH_URL = os.getenv("META_GRAPH_URL", "https://graph.facebook.com")
TIKTOK_API_URL = "https://open.tiktokapis.com"


def _env_true(name: str, default: str = "False") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _clean_hashtag(value: str) -> str:
    token = re.sub(r"[^0-9a-zA-Zа-яА-ЯіІїЇєЄґҐ_]", "", value.replace(" ", ""))
    return f"#{token}" if token else ""


def _unique(values: Iterable[str]) -> list:
    result = []
    seen = set()
    for value in values:
        if value and value.lower() not in seen:
            seen.add(value.lower())
            result.append(value)
    return result


def build_platform_metadata(script: Dict, seo: Dict) -> Dict[str, Dict]:
    """Create native-looking metadata instead of cloning one caption everywhere."""
    topic = str(script.get("topic") or script.get("niche_name") or "Цікавий факт")
    hook = str(script.get("hook") or seo.get("title") or topic).strip()
    payoff = str(script.get("payoff") or "").strip()
    niche = str(script.get("niche") or "цікаве")

    raw_tags = [
        niche,
        script.get("niche_name", ""),
        *script.get("keywords", [])[:4],
        "українськийконтент",
    ]
    hashtags = _unique(_clean_hashtag(str(value)) for value in raw_tags)
    hashtags = [tag for tag in hashtags if tag][:5]
    tag_line = " ".join(hashtags)

    youtube_description = str(seo.get("description") or "")
    if "#Shorts" not in youtube_description:
        youtube_description = f"#Shorts\n\n{youtube_description}".strip()

    instagram_caption = "\n\n".join(filter(None, [
        hook,
        payoff,
        "Збережи, щоб не загубити, і надішли тому, кого це здивує.",
        tag_line,
    ]))[:2200]

    tiktok_caption = " ".join(filter(None, [
        hook.rstrip(".!?"),
        "Додивись до кінця й напиши свою версію.",
        tag_line,
    ]))[:2200]

    facebook_description = "\n\n".join(filter(None, [
        hook,
        payoff,
        "А ти про це знав/знала? Поділись думкою в коментарях.",
        tag_line,
    ]))[:5000]

    return {
        "youtube": {
            "title": str(seo.get("title") or hook)[:100],
            "description": youtube_description[:5000],
            "tags": list(seo.get("tags") or [])[:15],
            "category_id": str(seo.get("category_id") or "22"),
        },
        "instagram": {"caption": instagram_caption},
        "tiktok": {"caption": tiktok_caption},
        "facebook": {"description": facebook_description},
    }


def media_share_signature(video_id: str) -> str:
    """Opaque signature used by Meta to fetch one temporary rendered MP4."""
    secret = (
        os.getenv("MEDIA_SHARE_SECRET")
        or os.getenv("SECRET_KEY")
        or "local-development-media-secret"
    )
    return hmac.new(
        secret.encode("utf-8"), video_id.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]


def is_valid_media_signature(video_id: str, signature: str) -> bool:
    return hmac.compare_digest(media_share_signature(video_id), signature or "")


@dataclass
class PublishResult:
    platform: str
    status: str
    message: str = ""
    platform_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


class TikTokPublisher:
    """TikTok Content Posting API (inbox upload or audited direct post)."""

    name = "tiktok"

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.access_token = os.getenv("TIKTOK_ACCESS_TOKEN", "").strip()
        self.mode = os.getenv("TIKTOK_POST_MODE", "inbox").strip().lower()

    def is_configured(self) -> bool:
        return bool(self.access_token)

    def status(self) -> Dict:
        direct_approved = _env_true("TIKTOK_DIRECT_POST_APPROVED")
        return {
            "platform": self.name,
            "configured": self.is_configured(),
            "enabled": self.name in enabled_platforms(),
            "mode": self.mode,
            "ready": self.is_configured() and (self.mode != "direct" or direct_approved),
            "note": (
                "Direct Post увімкнено"
                if self.mode == "direct" and direct_approved
                else "Inbox: після upload підтвердьте публікацію у TikTok"
            ),
        }

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    @staticmethod
    def _checked_json(response: requests.Response) -> Dict:
        response.raise_for_status()
        payload = response.json()
        error = payload.get("error") or {}
        if error.get("code") not in (None, "", "ok"):
            raise RuntimeError(error.get("message") or error["code"])
        return payload

    def _creator_info(self) -> Dict:
        response = self.session.post(
            f"{TIKTOK_API_URL}/v2/post/publish/creator_info/query/",
            headers=self._headers(),
            json={},
            timeout=30,
        )
        return self._checked_json(response).get("data") or {}

    def publish(self, video_path: Path, metadata: Dict, video_id: str) -> PublishResult:
        if not self.is_configured():
            return PublishResult(self.name, "skipped", "TIKTOK_ACCESS_TOKEN не додано")
        if _env_true("TEST_MODE"):
            return PublishResult(self.name, "queued", "TEST_MODE", f"test-{video_id}")

        size = video_path.stat().st_size
        if size <= 0:
            raise RuntimeError("TikTok upload отримав порожній MP4")

        direct = self.mode == "direct"
        if direct and not _env_true("TIKTOK_DIRECT_POST_APPROVED"):
            raise RuntimeError(
                "Direct Post потребує аудиту TikTok; залиште TIKTOK_POST_MODE=inbox"
            )

        if direct:
            creator = self._creator_info()
            allowed = creator.get("privacy_level_options") or []
            privacy = os.getenv("TIKTOK_PRIVACY_LEVEL", "").strip()
            if not privacy:
                raise RuntimeError("Для Direct Post додайте TIKTOK_PRIVACY_LEVEL")
            if allowed and privacy not in allowed:
                raise RuntimeError(f"TikTok не дозволяє privacy_level={privacy}")

            payload = {
                "post_info": {
                    "title": metadata.get("caption", "")[:2200],
                    "privacy_level": privacy,
                    "disable_duet": _env_true("TIKTOK_DISABLE_DUET"),
                    "disable_stitch": _env_true("TIKTOK_DISABLE_STITCH"),
                    "disable_comment": _env_true("TIKTOK_DISABLE_COMMENTS"),
                    "video_cover_timestamp_ms": 1000,
                    "brand_content_toggle": False,
                    "brand_organic_toggle": False,
                    "is_aigc": True,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": size,
                    "chunk_size": size,
                    "total_chunk_count": 1,
                },
            }
            init_url = f"{TIKTOK_API_URL}/v2/post/publish/video/init/"
        else:
            payload = {
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": size,
                    "chunk_size": size,
                    "total_chunk_count": 1,
                }
            }
            init_url = f"{TIKTOK_API_URL}/v2/post/publish/inbox/video/init/"

        init_response = self.session.post(
            init_url,
            headers=self._headers(),
            json=payload,
            timeout=45,
        )
        data = self._checked_json(init_response).get("data") or {}
        upload_url = data.get("upload_url")
        publish_id = data.get("publish_id")
        if not upload_url or not publish_id:
            raise RuntimeError("TikTok не повернув upload_url/publish_id")

        with video_path.open("rb") as video_file:
            upload_response = self.session.put(
                upload_url,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(size),
                    "Content-Range": f"bytes 0-{size - 1}/{size}",
                },
                data=video_file,
                timeout=300,
            )
        upload_response.raise_for_status()

        if direct:
            return PublishResult(
                self.name, "processing", "TikTok обробляє Direct Post", publish_id
            )
        return PublishResult(
            self.name,
            "awaiting_user",
            "Відео надіслано в TikTok Inbox; відкрийте сповіщення та підтвердьте пост",
            publish_id,
        )


class InstagramPublisher:
    """Instagram Reels publishing through the official Graph API."""

    name = "instagram"

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
        self.user_id = os.getenv("INSTAGRAM_USER_ID", "").strip()
        self.public_base_url = (
            os.getenv("PUBLIC_BASE_URL")
            or os.getenv("RENDER_EXTERNAL_URL")
            or ""
        ).strip().rstrip("/")

    def is_configured(self) -> bool:
        return bool(self.access_token and self.user_id and self.public_base_url)

    def status(self) -> Dict:
        return {
            "platform": self.name,
            "configured": self.is_configured(),
            "enabled": self.name in enabled_platforms(),
            "ready": self.is_configured(),
            "note": "Потрібні професійний Instagram, user ID і access token",
        }

    def publish(self, video_path: Path, metadata: Dict, video_id: str) -> PublishResult:
        if not self.is_configured():
            return PublishResult(
                self.name,
                "skipped",
                "Додайте INSTAGRAM_USER_ID, INSTAGRAM_ACCESS_TOKEN і PUBLIC_BASE_URL",
            )
        if _env_true("TEST_MODE"):
            return PublishResult(
                self.name,
                "published",
                "TEST_MODE",
                f"test-{video_id}",
                "https://instagram.com/reel/test",
            )

        signature = media_share_signature(video_id)
        video_url = f"{self.public_base_url}/api/media/{video_id}/{signature}.mp4"
        endpoint = f"{META_GRAPH_URL}/{META_GRAPH_VERSION}/{self.user_id}/media"
        create = self.session.post(
            endpoint,
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": metadata.get("caption", "")[:2200],
                "share_to_feed": "true",
                "access_token": self.access_token,
            },
            timeout=45,
        )
        create.raise_for_status()
        container_id = create.json().get("id")
        if not container_id:
            raise RuntimeError(f"Instagram не створив media container: {create.text[:300]}")

        attempts = max(3, int(os.getenv("INSTAGRAM_STATUS_ATTEMPTS", "36")))
        interval = max(1, int(os.getenv("INSTAGRAM_STATUS_INTERVAL", "5")))
        status_url = f"{META_GRAPH_URL}/{META_GRAPH_VERSION}/{container_id}"
        for _ in range(attempts):
            status_response = self.session.get(
                status_url,
                params={
                    "fields": "status_code,status",
                    "access_token": self.access_token,
                },
                timeout=30,
            )
            status_response.raise_for_status()
            status_data = status_response.json()
            status_code = str(status_data.get("status_code") or "").upper()
            if status_code == "FINISHED":
                break
            if status_code in {"ERROR", "EXPIRED"}:
                raise RuntimeError(status_data.get("status") or status_code)
            time.sleep(interval)
        else:
            raise RuntimeError("Instagram не обробив Reel у відведений час")

        publish_response = self.session.post(
            f"{META_GRAPH_URL}/{META_GRAPH_VERSION}/{self.user_id}/media_publish",
            data={"creation_id": container_id, "access_token": self.access_token},
            timeout=45,
        )
        publish_response.raise_for_status()
        media_id = publish_response.json().get("id")
        if not media_id:
            raise RuntimeError(f"Instagram не опублікував Reel: {publish_response.text[:300]}")

        permalink = None
        details = self.session.get(
            f"{META_GRAPH_URL}/{META_GRAPH_VERSION}/{media_id}",
            params={"fields": "permalink", "access_token": self.access_token},
            timeout=30,
        )
        if details.ok:
            permalink = details.json().get("permalink")
        return PublishResult(
            self.name, "published", "Reel опубліковано", media_id, permalink
        )


class FacebookPublisher:
    """Facebook Page Reels publishing through the official Video API."""

    name = "facebook"

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.access_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
        self.page_id = os.getenv("FACEBOOK_PAGE_ID", "").strip()

    def is_configured(self) -> bool:
        return bool(self.access_token and self.page_id)

    def status(self) -> Dict:
        return {
            "platform": self.name,
            "configured": self.is_configured(),
            "enabled": self.name in enabled_platforms(),
            "ready": self.is_configured(),
            "note": "Потрібні Facebook Page ID і Page access token",
        }

    def publish(self, video_path: Path, metadata: Dict, video_id: str) -> PublishResult:
        if not self.is_configured():
            return PublishResult(
                self.name, "skipped", "Додайте FACEBOOK_PAGE_ID і PAGE_ACCESS_TOKEN"
            )
        if _env_true("TEST_MODE"):
            return PublishResult(
                self.name,
                "published",
                "TEST_MODE",
                f"test-{video_id}",
                "https://facebook.com/reel/test",
            )

        endpoint = f"{META_GRAPH_URL}/{META_GRAPH_VERSION}/{self.page_id}/video_reels"
        start = self.session.post(
            endpoint,
            data={"upload_phase": "start", "access_token": self.access_token},
            timeout=45,
        )
        start.raise_for_status()
        start_data = start.json()
        upload_url = start_data.get("upload_url")
        reel_id = start_data.get("video_id")
        if not upload_url or not reel_id:
            raise RuntimeError(f"Facebook не почав Reel upload: {start.text[:300]}")

        size = video_path.stat().st_size
        with video_path.open("rb") as video_file:
            upload = self.session.post(
                upload_url,
                headers={
                    "Authorization": f"OAuth {self.access_token}",
                    "offset": "0",
                    "file_size": str(size),
                    "Content-Type": "application/octet-stream",
                },
                data=video_file,
                timeout=300,
            )
        upload.raise_for_status()

        finish = self.session.post(
            endpoint,
            data={
                "upload_phase": "finish",
                "video_id": reel_id,
                "video_state": "PUBLISHED",
                "description": metadata.get("description", "")[:5000],
                "access_token": self.access_token,
            },
            timeout=45,
        )
        finish.raise_for_status()
        if finish.json().get("success") is False:
            raise RuntimeError(f"Facebook не опублікував Reel: {finish.text[:300]}")

        permalink = None
        details = self.session.get(
            f"{META_GRAPH_URL}/{META_GRAPH_VERSION}/{reel_id}",
            params={"fields": "permalink_url", "access_token": self.access_token},
            timeout=30,
        )
        if details.ok:
            permalink = details.json().get("permalink_url")
        return PublishResult(
            self.name, "published", "Facebook Reel опубліковано", reel_id, permalink
        )


def enabled_platforms() -> list[str]:
    configured = os.getenv("AUTO_PUBLISH_PLATFORMS", "").strip()
    if configured:
        platforms = [item.strip().lower() for item in configured.split(",")]
    else:
        platforms = ["youtube"]
    supported = {"youtube", "tiktok", "instagram", "facebook"}
    return _unique(item for item in platforms if item in supported)


class UniversalPublisher:
    """Publish a rendered file to every enabled destination independently."""

    def __init__(self, youtube_uploader=None):
        self.youtube = youtube_uploader
        self.tiktok = TikTokPublisher()
        self.instagram = InstagramPublisher()
        self.facebook = FacebookPublisher()

    def get_status(self) -> Dict:
        youtube_configured = bool(self.youtube and self.youtube.is_configured())
        youtube = {
            "platform": "youtube",
            "configured": youtube_configured,
            "enabled": "youtube" in enabled_platforms(),
            "ready": youtube_configured,
            "note": "Підключення через Google OAuth на Dashboard",
        }
        statuses = [
            youtube,
            self.tiktok.status(),
            self.instagram.status(),
            self.facebook.status(),
        ]
        return {
            "auto_publish": _env_true("AUTO_UPLOAD"),
            "enabled_platforms": enabled_platforms(),
            "platforms": statuses,
        }

    def publish_all(
        self,
        video_path: Path,
        video_id: str,
        metadata: Dict[str, Dict],
    ) -> Dict[str, Dict]:
        results: Dict[str, Dict] = {}
        for platform in enabled_platforms():
            try:
                if platform == "youtube":
                    if not self.youtube or not self.youtube.is_configured():
                        result = PublishResult(
                            platform, "skipped", "YouTube ще не підключено"
                        )
                    else:
                        values = metadata[platform]
                        uploaded = self.youtube.upload_video(
                            video_path=video_path,
                            title=values["title"],
                            description=values["description"],
                            tags=values["tags"],
                            category_id=values["category_id"],
                        )
                        result = PublishResult(
                            platform,
                            "published",
                            "YouTube Short опубліковано",
                            uploaded.get("video_id"),
                            uploaded.get("url"),
                        )
                else:
                    adapter = getattr(self, platform)
                    result = adapter.publish(video_path, metadata[platform], video_id)
            except Exception as exc:
                logger.exception("%s publishing failed", platform)
                result = PublishResult(
                    platform, "failed", "Публікація не вдалася", error=str(exc)
                )
            results[platform] = result.to_dict()
        return results
