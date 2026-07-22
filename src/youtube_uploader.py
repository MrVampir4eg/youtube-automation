"""
YouTube Uploader
Автоматична публікація відео на YouTube через API
"""

import os
import logging
from pathlib import Path
from typing import Dict, Optional
import pickle
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Scopes для YouTube Data API
SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly'
]
TOKEN_URI = 'https://oauth2.googleapis.com/token'


class YouTubeUploader:
    """Публікація відео на YouTube"""

    def __init__(
        self,
        refresh_token: Optional[str] = None,
        use_token_file: bool = True,
        privacy_status: Optional[str] = None,
        allow_environment_token: bool = True,
    ):
        self.client_id = os.getenv('YOUTUBE_CLIENT_ID')
        self.client_secret = os.getenv('YOUTUBE_CLIENT_SECRET')
        self.redirect_uri = os.getenv('YOUTUBE_REDIRECT_URI', 'http://localhost:5000/oauth2callback')
        self.refresh_token = refresh_token
        self.privacy_status = privacy_status
        self.allow_environment_token = allow_environment_token

        project_root = Path(__file__).resolve().parents[1]
        self.token_file = (
            project_root / 'config' / 'youtube_token.pickle'
            if use_token_file else None
        )

        self.youtube = None

        # Статистика
        self.videos_uploaded_today = 0
        self.total_uploads = 0

    def _ensure_authenticated(self):
        """Lazy OAuth: не блокує запуск вебсервера без YouTube credentials."""
        if self.youtube is None:
            self._authenticate()

    def get_oauth_client_config(self) -> Dict:
        """Конфігурація Google OAuth для web application."""
        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                'Додайте YOUTUBE_CLIENT_ID і YOUTUBE_CLIENT_SECRET у Render Environment'
            )

        return {
            'web': {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uris': [self.redirect_uri],
                'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                'token_uri': TOKEN_URI
            }
        }

    def is_configured(self) -> bool:
        """Чи є довгостроковий token для автозавантаження."""
        return bool(
            self.client_id
            and self.client_secret
            and (
                self.refresh_token
                or (
                    self.allow_environment_token
                    and os.getenv('YOUTUBE_REFRESH_TOKEN')
                )
                or (self.token_file is not None and self.token_file.exists())
            )
        )

    def set_credentials(self, creds: Credentials):
        """Зберегти OAuth credentials для поточного instance."""
        if self.token_file is not None:
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with self.token_file.open('wb') as token:
                pickle.dump(creds, token)
        self.youtube = build(
            'youtube',
            'v3',
            credentials=creds,
            cache_discovery=False
        )

    def _authenticate(self):
        """OAuth 2.0 через refresh token з Render Environment."""
        self.get_oauth_client_config()
        creds = None

        refresh_token = self.refresh_token or (
            os.getenv('YOUTUBE_REFRESH_TOKEN')
            if self.allow_environment_token else None
        )
        if refresh_token:
            creds = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri=TOKEN_URI,
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=SCOPES
            )

        # Token-файл дає змогу завантажувати одразу після callback,
        # але для переживання redeploy token треба зберегти в Render.
        if creds is None and self.token_file is not None and self.token_file.exists():
            try:
                with self.token_file.open('rb') as token:
                    creds = pickle.load(token)
            except Exception as exc:
                logger.warning(f'Failed to load YouTube token file: {exc}')

        if creds is None:
            raise RuntimeError(
                'Спочатку підключіть YouTube на сторінці /youtube/connect'
            )

        if not creds.valid:
            if not creds.refresh_token:
                raise RuntimeError('Немає YouTube refresh token; підключіть канал повторно')
            logger.info('Refreshing YouTube access token...')
            creds.refresh(Request())

        self.set_credentials(creds)
        logger.info("✓ YouTube API authenticated")

    def upload_video(self,
                    video_path: Path,
                    title: str,
                    description: str,
                    tags: list,
                    category_id: str = '22',
                    privacy_status: str = 'public',
                    made_for_kids: bool = False,
                    contains_synthetic_media: bool = True) -> Dict:
        """
        Завантаження відео на YouTube

        Args:
            video_path: Шлях до відео файлу
            title: Заголовок (max 100 chars)
            description: Опис (max 5000 chars)
            tags: Список тегів (max 500 chars total)
            category_id: ID категорії (22 = People & Blogs)
            privacy_status: 'public', 'private', або 'unlisted'
            made_for_kids: Чи контент для дітей

        Returns:
            {
                'video_id': str,
                'url': str,
                'title': str,
                'published_at': str
            }
        """

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Тестовий режим - не публікуємо реально
        if os.getenv('TEST_MODE', 'False').lower() == 'true':
            logger.info(f"TEST MODE: Would upload {video_path.name}")
            return {
                'video_id': f'TEST_{int(datetime.now().timestamp())}',
                'url': 'https://youtube.com/test',
                'title': title,
                'published_at': datetime.utcnow().isoformat(),
                'test_mode': True
            }

        self._ensure_authenticated()
        privacy_status = (
            self.privacy_status
            or os.getenv('YOUTUBE_PRIVACY_STATUS', privacy_status)
        )

        logger.info(f"Uploading video: {video_path.name}")
        logger.info(f"Title: {title[:50]}...")

        try:
            # Metadata
            body = {
                'snippet': {
                    'title': title[:100],  # YouTube limit
                    'description': description[:5000],
                    'tags': tags[:15],  # Max 15 tags
                    'categoryId': category_id,
                    'defaultLanguage': 'uk',  # Українська
                    'defaultAudioLanguage': 'uk'
                },
                'status': {
                    'privacyStatus': privacy_status,
                    'selfDeclaredMadeForKids': made_for_kids,
                    'containsSyntheticMedia': bool(contains_synthetic_media),
                }
            }

            # Додаємо #Shorts до опису якщо ще немає
            if '#Shorts' not in body['snippet']['description']:
                body['snippet']['description'] = '#Shorts\n\n' + body['snippet']['description']

            # Media upload
            media = MediaFileUpload(
                str(video_path),
                mimetype='video/mp4',
                resumable=True,
                chunksize=1024*1024  # 1MB chunks
            )

            # Insert request
            request = self.youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )

            # Upload з progress tracking
            response = None
            upload_progress = 0

            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    if progress > upload_progress + 10:  # Log every 10%
                        logger.info(f"Upload progress: {progress}%")
                        upload_progress = progress

            video_id = response['id']
            video_url = f"https://youtube.com/shorts/{video_id}"

            self.videos_uploaded_today += 1
            self.total_uploads += 1

            logger.info(f"✓ Video uploaded: {video_id}")
            logger.info(f"  URL: {video_url}")

            return {
                'video_id': video_id,
                'url': video_url,
                'title': title,
                'published_at': response.get('snippet', {}).get(
                    'publishedAt',
                    datetime.utcnow().isoformat()
                ),
                'privacy_status': privacy_status
            }

        except HttpError as e:
            logger.error(f"YouTube API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Upload error: {e}")
            raise

    def update_video(self,
                    video_id: str,
                    title: Optional[str] = None,
                    description: Optional[str] = None,
                    tags: Optional[list] = None) -> Dict:
        """Оновлення метаданих відео"""

        self._ensure_authenticated()

        try:
            # Спочатку отримуємо поточні дані
            current = self.youtube.videos().list(
                part='snippet',
                id=video_id
            ).execute()

            if not current['items']:
                raise ValueError(f"Video not found: {video_id}")

            snippet = current['items'][0]['snippet']

            # Оновлюємо тільки те, що передали
            if title:
                snippet['title'] = title[:100]
            if description:
                snippet['description'] = description[:5000]
            if tags:
                snippet['tags'] = tags[:15]

            # Update request
            response = self.youtube.videos().update(
                part='snippet',
                body={
                    'id': video_id,
                    'snippet': snippet
                }
            ).execute()

            logger.info(f"✓ Video updated: {video_id}")

            return {
                'video_id': video_id,
                'title': response['snippet']['title'],
                'updated': True
            }

        except HttpError as e:
            logger.error(f"Update error: {e}")
            raise

    def get_video_analytics(self, video_id: str) -> Dict:
        """Отримання статистики відео"""

        self._ensure_authenticated()

        try:
            response = self.youtube.videos().list(
                part='statistics,snippet,contentDetails',
                id=video_id
            ).execute()

            if not response['items']:
                raise ValueError(f"Video not found: {video_id}")

            video = response['items'][0]
            stats = video['statistics']

            return {
                'video_id': video_id,
                'title': video['snippet']['title'],
                'published_at': video['snippet']['publishedAt'],
                'duration': video['contentDetails']['duration'],
                'views': int(stats.get('viewCount', 0)),
                'likes': int(stats.get('likeCount', 0)),
                'comments': int(stats.get('commentCount', 0)),
                'favorites': int(stats.get('favoriteCount', 0))
            }

        except HttpError as e:
            logger.error(f"Analytics error: {e}")
            return {}

    def get_channel_info(self) -> Dict:
        """Інформація про канал"""

        self._ensure_authenticated()

        try:
            response = self.youtube.channels().list(
                part='snippet,statistics,contentDetails',
                mine=True
            ).execute()

            if not response['items']:
                raise ValueError("No channel found")

            channel = response['items'][0]
            stats = channel['statistics']

            return {
                'channel_id': channel['id'],
                'title': channel['snippet']['title'],
                'handle': channel['snippet'].get('customUrl'),
                'description': channel['snippet']['description'],
                'subscribers': int(stats.get('subscriberCount', 0)),
                'total_views': int(stats.get('viewCount', 0)),
                'video_count': int(stats.get('videoCount', 0)),
                'created_at': channel['snippet']['publishedAt']
            }

        except HttpError as e:
            logger.error(f"Channel info error: {e}")
            return {}

    def list_my_videos(self, max_results: int = 50) -> list:
        """Список моїх відео"""

        self._ensure_authenticated()

        try:
            # Спочатку отримуємо uploads playlist ID
            channel = self.youtube.channels().list(
                part='contentDetails',
                mine=True
            ).execute()

            uploads_playlist_id = channel['items'][0]['contentDetails']['relatedPlaylists']['uploads']

            # Отримуємо відео з playlist
            response = self.youtube.playlistItems().list(
                part='snippet,contentDetails',
                playlistId=uploads_playlist_id,
                maxResults=max_results
            ).execute()

            videos = []
            for item in response['items']:
                videos.append({
                    'video_id': item['contentDetails']['videoId'],
                    'title': item['snippet']['title'],
                    'published_at': item['snippet']['publishedAt'],
                    'thumbnail': item['snippet']['thumbnails']['default']['url']
                })

            return videos

        except HttpError as e:
            logger.error(f"List videos error: {e}")
            return []

    def delete_video(self, video_id: str) -> bool:
        """Видалення відео (будьте обережні!)"""

        self._ensure_authenticated()

        try:
            self.youtube.videos().delete(id=video_id).execute()
            logger.info(f"✓ Video deleted: {video_id}")
            return True

        except HttpError as e:
            logger.error(f"Delete error: {e}")
            return False

    def get_quota_usage(self) -> Dict:
        """
        Оцінка використання YouTube API квоти

        YouTube дає 10,000 units/день
        - Upload: 1,600 units
        - Update: 50 units
        - List: 1 unit
        """

        # Приблизна оцінка на основі операцій
        estimated_quota = (
            self.videos_uploaded_today * 1600 +  # Uploads
            self.total_uploads * 1  # Lists для verification
        )

        return {
            'estimated_used': estimated_quota,
            'daily_limit': 10000,
            'remaining': 10000 - estimated_quota,
            'uploads_today': self.videos_uploaded_today,
            'max_uploads_remaining': (10000 - estimated_quota) // 1600
        }


class UploadScheduler:
    """
    Scheduler для оптимального часу публікації
    """

    def __init__(self):
        # Найкращі часи для публікації (UTC)
        self.optimal_hours = [12, 14, 16, 18, 20]  # Peak hours

    def get_next_upload_time(self) -> datetime:
        """Визначення наступного оптимального часу"""
        from datetime import datetime, timedelta
        import pytz

        now = datetime.now(pytz.UTC)
        current_hour = now.hour

        # Знаходимо наступний optimal hour
        next_hours = [h for h in self.optimal_hours if h > current_hour]

        if next_hours:
            next_hour = next_hours[0]
            next_time = now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
        else:
            # Якщо сьогодні вже пізно, планує на завтра
            next_hour = self.optimal_hours[0]
            next_time = (now + timedelta(days=1)).replace(
                hour=next_hour, minute=0, second=0, microsecond=0
            )

        return next_time

    def should_upload_now(self) -> bool:
        """Чи зараз оптимальний час для публікації?"""
        from datetime import datetime
        import pytz

        now = datetime.now(pytz.UTC)
        return now.hour in self.optimal_hours


if __name__ == '__main__':
    # Тестування
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    uploader = YouTubeUploader()

    # Отримуємо інфо про канал
    print("\n📺 Channel Info:")
    channel = uploader.get_channel_info()
    if channel:
        print(f"  Назва: {channel['title']}")
        print(f"  Підписників: {channel['subscribers']:,}")
        print(f"  Всього переглядів: {channel['total_views']:,}")
        print(f"  Відео: {channel['video_count']}")

    # Quota usage
    quota = uploader.get_quota_usage()
    print(f"\n📊 Quota Usage:")
    print(f"  Використано: {quota['estimated_used']:,} / {quota['daily_limit']:,}")
    print(f"  Залишилось завантажень: {quota['max_uploads_remaining']}")

    # Тест upload (якщо є відео)
    test_video = Path('output/videos/test_render_001.mp4')
    if test_video.exists():
        print(f"\n🚀 Test Upload:")
        print(f"  Файл: {test_video.name}")

        result = uploader.upload_video(
            video_path=test_video,
            title="Test YouTube Shorts - Автоматична генерація",
            description="Це тестове відео згенероване автоматично через AI.\n\n#Shorts #AI #Test",
            tags=['shorts', 'test', 'ai', 'automation'],
            privacy_status='private'  # Private для тесту
        )

        print(f"\n✓ Uploaded!")
        print(f"  Video ID: {result['video_id']}")
        print(f"  URL: {result['url']}")
    else:
        print("\n⚠ Немає тестового відео для завантаження")
