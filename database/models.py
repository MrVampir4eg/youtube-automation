"""
Database Models
SQLite база даних для зберігання відео та статистики
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class Database:
    """SQLite база даних"""

    def __init__(self, db_path: str = 'youtube_automation.db'):
        self.db_path = Path(db_path)
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

            CREATE INDEX IF NOT EXISTS idx_videos_niche ON videos(niche);
            CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at);
            CREATE INDEX IF NOT EXISTS idx_analytics_video ON analytics(video_id);
            CREATE INDEX IF NOT EXISTS idx_analytics_checked ON analytics(checked_at);
        """)

        # Безпечна міграція старої Render SQLite без видалення даних.
        columns = {
            row['name']
            for row in self.conn.execute("PRAGMA table_info(videos)").fetchall()
        }
        if 'platform_results' not in columns:
            self.conn.execute("ALTER TABLE videos ADD COLUMN platform_results TEXT")

        self.conn.commit()
        logger.info(f"✓ Database initialized: {self.db_path}")

    def add_video(self, video_data: Dict) -> int:
        """Додати відео"""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO videos (
                video_id, niche, title, description, script,
                video_path, audio_path, duration, filesize,
                youtube_video_id, youtube_url, platform_results, ai_cost, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            video_data['created_at']
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
