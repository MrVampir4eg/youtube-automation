"""
Database Models
SQLite база даних для зберігання відео та статистики
"""

import sqlite3
import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone
import json
import logging

logger = logging.getLogger(__name__)


class Database:
    """SQLite база даних"""

    def __init__(self, db_path: Optional[str] = None):
        # DATABASE_PATH can point at a Render persistent disk, for example
        # /var/data/youtube_automation.db. DATABASE_URL is kept for backward
        # compatibility with the old SQLite-only configuration.
        configured = db_path or os.getenv('DATABASE_PATH', '').strip()
        if not configured:
            database_url = os.getenv('DATABASE_URL', '').strip()
            configured = (
                database_url.removeprefix('sqlite:///')
                if database_url.startswith('sqlite:///')
                else 'youtube_automation.db'
            )
        self.db_path = Path(configured)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = None
        self._init_db()

    def _init_db(self):
        """Ініціалізація бази даних"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Повертати dict замість tuple

        # Створення таблиць
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT UNIQUE NOT NULL,
                niche TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                script TEXT,
                video_path TEXT,
                audio_path TEXT,
                duration REAL,
                filesize INTEGER,
                youtube_video_id TEXT,
                youtube_url TEXT,
                platform_results TEXT,
                ai_cost REAL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                youtube_video_id TEXT NOT NULL,
                views INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                watch_time REAL DEFAULT 0,
                ctr REAL DEFAULT 0,
                checked_at TEXT NOT NULL,
                FOREIGN KEY (video_id) REFERENCES videos(video_id)
            );

            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                videos_created INTEGER DEFAULT 0,
                videos_uploaded INTEGER DEFAULT 0,
                total_views INTEGER DEFAULT 0,
                total_revenue REAL DEFAULT 0,
                total_cost REAL DEFAULT 0,
                profit REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT,
                error_type TEXT,
                error_message TEXT,
                stack_trace TEXT,
                occurred_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS channel_profiles (
                profile_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                youtube_refresh_token TEXT,
                youtube_channel_id TEXT,
                youtube_channel_title TEXT,
                youtube_channel_handle TEXT,
                default_content_mode TEXT DEFAULT 'organic',
                default_offer_id TEXT,
                default_niche TEXT,
                privacy_status TEXT DEFAULT 'public',
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS affiliate_offers (
                offer_id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                description TEXT NOT NULL,
                keywords TEXT,
                cta TEXT,
                disclosure TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (profile_id) REFERENCES channel_profiles(profile_id)
            );

            CREATE INDEX IF NOT EXISTS idx_videos_niche ON videos(niche);
            CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at);
            CREATE INDEX IF NOT EXISTS idx_analytics_video ON analytics(video_id);
            CREATE INDEX IF NOT EXISTS idx_analytics_checked ON analytics(checked_at);
            CREATE INDEX IF NOT EXISTS idx_offers_profile ON affiliate_offers(profile_id);
        """)

        # Безпечна міграція старої Render SQLite без видалення даних.
        columns = {
            row['name']
            for row in self.conn.execute("PRAGMA table_info(videos)").fetchall()
        }
        if 'platform_results' not in columns:
            self.conn.execute("ALTER TABLE videos ADD COLUMN platform_results TEXT")
        for column, definition in {
            'content_mode': "TEXT DEFAULT 'organic'",
            'profile_id': "TEXT DEFAULT 'default'",
            'affiliate_offer_id': 'TEXT',
        }.items():
            if column not in columns:
                self.conn.execute(f"ALTER TABLE videos ADD COLUMN {column} {definition}")

        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT OR IGNORE INTO channel_profiles (
                profile_id, name, default_content_mode, privacy_status,
                enabled, created_at, updated_at
            ) VALUES ('default', 'Основний канал', 'organic', 'public', 1, ?, ?)
            """,
            (now, now),
        )

        self.conn.commit()
        logger.info(f"✓ Database initialized: {self.db_path}")

    def add_video(self, video_data: Dict) -> int:
        """Додати відео"""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO videos (
                video_id, niche, title, description, script,
                video_path, audio_path, duration, filesize,
                youtube_video_id, youtube_url, platform_results, ai_cost, created_at,
                content_mode, profile_id, affiliate_offer_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            video_data['video_id'],
            video_data['niche'],
            video_data['title'],
            video_data['description'],
            video_data['script'],
            video_data['video_path'],
            video_data['audio_path'],
            video_data['duration'],
            video_data['filesize'],
            video_data.get('youtube_video_id'),
            video_data.get('youtube_url'),
            json.dumps(video_data.get('platform_results', {}), ensure_ascii=False),
            video_data.get('ai_cost', 0),
            video_data['created_at'],
            video_data.get('content_mode', 'organic'),
            video_data.get('profile_id', 'default'),
            video_data.get('affiliate_offer_id')
        ))

        self.conn.commit()
        return cursor.lastrowid

    def get_video(self, video_id: str) -> Optional[Dict]:
        """Отримати відео по ID"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,))
        row = cursor.fetchone()
        return self._video_row(row) if row else None

    def list_videos(self, limit: int = 50, niche: Optional[str] = None) -> List[Dict]:
        """Список відео"""
        cursor = self.conn.cursor()

        if niche:
            cursor.execute("""
                SELECT * FROM videos WHERE niche = ?
                ORDER BY created_at DESC LIMIT ?
            """, (niche, limit))
        else:
            cursor.execute("""
                SELECT * FROM videos ORDER BY created_at DESC LIMIT ?
            """, (limit,))

        return [self._video_row(row) for row in cursor.fetchall()]

    @staticmethod
    def _video_row(row: sqlite3.Row) -> Dict:
        video = dict(row)
        raw_results = video.get('platform_results')
        if isinstance(raw_results, str):
            try:
                video['platform_results'] = json.loads(raw_results) if raw_results else {}
            except json.JSONDecodeError:
                video['platform_results'] = {}
        elif raw_results is None:
            video['platform_results'] = {}
        return video

    def update_analytics(self, video_id: str, youtube_video_id: str, analytics: Dict):
        """Оновити аналітику відео"""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO analytics (
                video_id, youtube_video_id, views, likes, comments,
                checked_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            video_id,
            youtube_video_id,
            analytics.get('views', 0),
            analytics.get('likes', 0),
            analytics.get('comments', 0),
            datetime.utcnow().isoformat()
        ))

        self.conn.commit()

    def get_latest_analytics(self, video_id: str) -> Optional[Dict]:
        """Остання аналітика відео"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM analytics WHERE video_id = ?
            ORDER BY checked_at DESC LIMIT 1
        """, (video_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_analytics_history(self, video_id: str) -> List[Dict]:
        """Історія аналітики"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM analytics WHERE video_id = ?
            ORDER BY checked_at ASC
        """, (video_id,))
        return [dict(row) for row in cursor.fetchall()]

    def update_daily_stats(self, date: str, stats: Dict):
        """Оновити денну статистику"""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO daily_stats (
                date, videos_created, videos_uploaded, total_views,
                total_revenue, total_cost, profit
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            date,
            stats.get('videos_created', 0),
            stats.get('videos_uploaded', 0),
            stats.get('total_views', 0),
            stats.get('total_revenue', 0),
            stats.get('total_cost', 0),
            stats.get('profit', 0)
        ))

        self.conn.commit()

    def get_daily_stats(self, days: int = 30) -> List[Dict]:
        """Денна статистика за період"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM daily_stats
            ORDER BY date DESC LIMIT ?
        """, (days,))
        return [dict(row) for row in cursor.fetchall()]

    def log_error(self, video_id: Optional[str], error_type: str,
                  error_message: str, stack_trace: Optional[str] = None):
        """Логування помилок"""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO errors (video_id, error_type, error_message, stack_trace, occurred_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            video_id,
            error_type,
            error_message,
            stack_trace,
            datetime.utcnow().isoformat()
        ))

        self.conn.commit()

    def get_total_stats(self) -> Dict:
        """Загальна статистика"""
        cursor = self.conn.cursor()

        # Загальна кількість відео
        cursor.execute("SELECT COUNT(*) as total FROM videos")
        total_videos = cursor.fetchone()['total']

        # Завантажені на YouTube
        cursor.execute("SELECT COUNT(*) as total FROM videos WHERE youtube_video_id IS NOT NULL")
        uploaded_videos = cursor.fetchone()['total']

        # Загальна вартість
        cursor.execute("SELECT SUM(ai_cost) as total FROM videos")
        total_cost = cursor.fetchone()['total'] or 0

        # По нішах
        cursor.execute("""
            SELECT niche, COUNT(*) as count
            FROM videos
            GROUP BY niche
            ORDER BY count DESC
        """)
        by_niche = [dict(row) for row in cursor.fetchall()]

        return {
            'total_videos': total_videos,
            'uploaded_videos': uploaded_videos,
            'total_cost': round(total_cost, 2),
            'by_niche': by_niche
        }

    def close(self):
        """Закрити з'єднання"""
        if self.conn:
            self.conn.close()

    # ------------------------------------------------------------------
    # Channel profiles and affiliate offers
    # ------------------------------------------------------------------

    def list_channel_profiles(self, include_secrets: bool = False) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM channel_profiles WHERE enabled = 1 ORDER BY created_at ASC"
        ).fetchall()
        profiles = []
        for row in rows:
            profile = dict(row)
            profile['connected'] = bool(profile.get('youtube_refresh_token')) or (
                profile['profile_id'] == 'default'
                and bool(os.getenv('YOUTUBE_REFRESH_TOKEN'))
            )
            profile['enabled'] = bool(profile.get('enabled'))
            if not include_secrets:
                profile.pop('youtube_refresh_token', None)
            profiles.append(profile)
        return profiles

    def get_channel_profile(
        self, profile_id: str, include_secrets: bool = False
    ) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM channel_profiles WHERE profile_id = ? AND enabled = 1",
            (profile_id,),
        ).fetchone()
        if not row:
            return None
        profile = dict(row)
        if (
            profile_id == 'default'
            and not profile.get('youtube_refresh_token')
            and os.getenv('YOUTUBE_REFRESH_TOKEN')
        ):
            profile['youtube_refresh_token'] = os.getenv('YOUTUBE_REFRESH_TOKEN')
        profile['connected'] = bool(profile.get('youtube_refresh_token'))
        profile['enabled'] = bool(profile.get('enabled'))
        if not include_secrets:
            profile.pop('youtube_refresh_token', None)
        return profile

    def create_channel_profile(self, name: str) -> Dict:
        profile_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO channel_profiles (
                profile_id, name, default_content_mode, privacy_status,
                enabled, created_at, updated_at
            ) VALUES (?, ?, 'organic', 'public', 1, ?, ?)
            """,
            (profile_id, name.strip(), now, now),
        )
        self.conn.commit()
        return self.get_channel_profile(profile_id) or {}

    def save_channel_credentials(
        self,
        profile_id: str,
        refresh_token: str,
        channel_info: Optional[Dict] = None,
    ) -> None:
        info = channel_info or {}
        cursor = self.conn.execute(
            """
            UPDATE channel_profiles
            SET youtube_refresh_token = ?, youtube_channel_id = ?,
                youtube_channel_title = ?, youtube_channel_handle = ?,
                updated_at = ?
            WHERE profile_id = ? AND enabled = 1
            """,
            (
                refresh_token,
                info.get('channel_id'),
                info.get('title'),
                info.get('handle'),
                datetime.now(timezone.utc).isoformat(),
                profile_id,
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError('Профіль каналу не знайдено')
        self.conn.commit()

    def update_channel_profile(self, profile_id: str, values: Dict) -> Dict:
        allowed = {
            'name', 'default_content_mode', 'default_offer_id', 'default_niche',
            'privacy_status'
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return self.get_channel_profile(profile_id) or {}
        assignments = ', '.join(f'{key} = ?' for key in updates)
        params = [*updates.values(), datetime.now(timezone.utc).isoformat(), profile_id]
        cursor = self.conn.execute(
            f"UPDATE channel_profiles SET {assignments}, updated_at = ? "
            "WHERE profile_id = ? AND enabled = 1",
            params,
        )
        if cursor.rowcount != 1:
            raise ValueError('Профіль каналу не знайдено')
        self.conn.commit()
        return self.get_channel_profile(profile_id) or {}

    def create_affiliate_offer(self, profile_id: str, data: Dict) -> Dict:
        if not self.get_channel_profile(profile_id):
            raise ValueError('Профіль каналу не знайдено')
        offer_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO affiliate_offers (
                offer_id, profile_id, name, url, description, keywords,
                cta, disclosure, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                offer_id,
                profile_id,
                data['name'].strip(),
                data['url'].strip(),
                data['description'].strip(),
                json.dumps(data.get('keywords', []), ensure_ascii=False),
                data.get('cta', '').strip() or 'Посилання — в описі',
                data.get('disclosure', '').strip()
                or 'Партнерське посилання: я можу отримати комісію без доплати з вашого боку.',
                now,
                now,
            ),
        )
        self.conn.commit()
        return self.get_affiliate_offer(offer_id) or {}

    def list_affiliate_offers(self, profile_id: Optional[str] = None) -> List[Dict]:
        if profile_id:
            rows = self.conn.execute(
                """SELECT * FROM affiliate_offers
                   WHERE enabled = 1 AND profile_id = ? ORDER BY created_at DESC""",
                (profile_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM affiliate_offers WHERE enabled = 1 ORDER BY created_at DESC"
            ).fetchall()
        return [self._offer_row(row) for row in rows]

    def get_affiliate_offer(self, offer_id: str) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM affiliate_offers WHERE offer_id = ? AND enabled = 1",
            (offer_id,),
        ).fetchone()
        return self._offer_row(row) if row else None

    @staticmethod
    def _offer_row(row: sqlite3.Row) -> Dict:
        offer = dict(row)
        try:
            offer['keywords'] = json.loads(offer.get('keywords') or '[]')
        except json.JSONDecodeError:
            offer['keywords'] = []
        offer['enabled'] = bool(offer.get('enabled'))
        return offer

    def __del__(self):
        self.close()


class Video:
    """Helper клас для роботи з відео"""

    @staticmethod
    def to_dict(row: sqlite3.Row) -> Dict:
        """Конвертація Row в Dict"""
        return dict(row)


if __name__ == '__main__':
    # Тестування
    logging.basicConfig(level=logging.INFO)

    db = Database('test.db')

    # Тестові дані
    test_video = {
        'video_id': 'test123',
        'niche': 'motivation',
        'title': 'Test Video',
        'description': 'Test description',
        'script': 'Test script...',
        'video_path': '/path/to/video.mp4',
        'audio_path': '/path/to/audio.mp3',
        'duration': 45.5,
        'filesize': 5242880,
        'youtube_video_id': 'abc123xyz',
        'youtube_url': 'https://youtube.com/shorts/abc123xyz',
        'ai_cost': 0.025,
        'created_at': datetime.utcnow().isoformat()
    }

    # Додати відео
    db.add_video(test_video)
    print("✓ Video added")

    # Отримати відео
    video = db.get_video('test123')
    print(f"✓ Video retrieved: {video['title']}")

    # Загальна статистика
    stats = db.get_total_stats()
    print(f"\n📊 Stats:")
    print(f"  Total videos: {stats['total_videos']}")
    print(f"  Uploaded: {stats['uploaded_videos']}")
    print(f"  Total cost: ${stats['total_cost']}")

    # Cleanup
    Path('test.db').unlink()
    print("\n✓ Test complete")
