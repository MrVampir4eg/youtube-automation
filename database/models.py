"""
Database Models
SQLite база даних для зберігання відео та статистики
"""

import sqlite3
import os
import uuid
import math
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
                advertiser_name TEXT,
                campaign_type TEXT DEFAULT 'affiliate',
                status TEXT DEFAULT 'active',
                url TEXT NOT NULL,
                description TEXT NOT NULL,
                keywords TEXT,
                cta TEXT,
                disclosure TEXT,
                payout_model TEXT DEFAULT 'CPS',
                payout_value REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                budget_total REAL DEFAULT 0,
                starts_at TEXT,
                ends_at TEXT,
                tracking_slug TEXT,
                approved_claims TEXT,
                prohibited_claims TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (profile_id) REFERENCES channel_profiles(profile_id)
            );

            CREATE TABLE IF NOT EXISTS affiliate_clicks (
                click_id TEXT PRIMARY KEY,
                offer_id TEXT NOT NULL,
                video_id TEXT,
                platform TEXT,
                sub_id TEXT,
                referrer TEXT,
                user_agent TEXT,
                ip_hash TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (offer_id) REFERENCES affiliate_offers(offer_id)
            );

            CREATE TABLE IF NOT EXISTS ad_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                offer_id TEXT NOT NULL,
                video_id TEXT,
                event_type TEXT NOT NULL,
                amount REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                source TEXT DEFAULT 'manual',
                external_ref TEXT,
                referrer_host TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (offer_id) REFERENCES affiliate_offers(offer_id)
            );

            CREATE TABLE IF NOT EXISTS advertiser_leads (
                lead_id TEXT PRIMARY KEY,
                contact_name TEXT NOT NULL,
                email TEXT NOT NULL,
                company TEXT NOT NULL,
                website TEXT,
                budget REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                objective TEXT,
                notes TEXT,
                status TEXT DEFAULT 'new',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS affiliate_conversions (
                conversion_id TEXT PRIMARY KEY,
                offer_id TEXT NOT NULL,
                video_id TEXT,
                platform TEXT,
                order_id TEXT,
                amount REAL NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'USD',
                status TEXT NOT NULL DEFAULT 'approved',
                source TEXT NOT NULL DEFAULT 'manual',
                occurred_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (source, order_id),
                FOREIGN KEY (offer_id) REFERENCES affiliate_offers(offer_id)
            );

            CREATE TABLE IF NOT EXISTS admin_users (
                admin_id INTEGER PRIMARY KEY CHECK (admin_id = 1),
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                last_login_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token_id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (admin_id) REFERENCES admin_users(admin_id)
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS automation_runs (
                run_id TEXT PRIMARY KEY,
                trigger_source TEXT NOT NULL,
                profile_id TEXT,
                content_mode TEXT,
                status TEXT NOT NULL,
                message TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_videos_niche ON videos(niche);
            CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at);
            CREATE INDEX IF NOT EXISTS idx_analytics_video ON analytics(video_id);
            CREATE INDEX IF NOT EXISTS idx_analytics_checked ON analytics(checked_at);
            CREATE INDEX IF NOT EXISTS idx_offers_profile ON affiliate_offers(profile_id);
            CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_offer ON affiliate_clicks(offer_id);
            CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_video ON affiliate_clicks(video_id);
            CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_created ON affiliate_clicks(created_at);
            CREATE INDEX IF NOT EXISTS idx_affiliate_conversions_offer ON affiliate_conversions(offer_id);
            CREATE INDEX IF NOT EXISTS idx_affiliate_conversions_video ON affiliate_conversions(video_id);
            CREATE INDEX IF NOT EXISTS idx_affiliate_conversions_occurred ON affiliate_conversions(occurred_at);
            CREATE INDEX IF NOT EXISTS idx_ad_events_offer ON ad_events(offer_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_ad_events_video ON ad_events(video_id);
            CREATE INDEX IF NOT EXISTS idx_ad_leads_status ON advertiser_leads(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_reset_token_hash ON password_reset_tokens(token_hash);
            CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
            CREATE INDEX IF NOT EXISTS idx_automation_created ON automation_runs(created_at);
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

        offer_columns = {
            row['name']
            for row in self.conn.execute("PRAGMA table_info(affiliate_offers)").fetchall()
        }
        for column, definition in {
            'advertiser_name': 'TEXT',
            'campaign_type': "TEXT DEFAULT 'affiliate'",
            'status': "TEXT DEFAULT 'active'",
            'payout_model': "TEXT DEFAULT 'CPS'",
            'payout_value': 'REAL DEFAULT 0',
            'currency': "TEXT DEFAULT 'USD'",
            'budget_total': 'REAL DEFAULT 0',
            'starts_at': 'TEXT',
            'ends_at': 'TEXT',
            'tracking_slug': 'TEXT',
            'approved_claims': 'TEXT',
            'prohibited_claims': 'TEXT',
        }.items():
            if column not in offer_columns:
                self.conn.execute(
                    f"ALTER TABLE affiliate_offers ADD COLUMN {column} {definition}"
                )
        self.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_offers_tracking_slug "
            "ON affiliate_offers(tracking_slug)"
        )
        legacy_offers = self.conn.execute(
            "SELECT offer_id FROM affiliate_offers WHERE tracking_slug IS NULL"
        ).fetchall()
        for legacy in legacy_offers:
            self.conn.execute(
                "UPDATE affiliate_offers SET tracking_slug = ? WHERE offer_id = ?",
                (uuid.uuid4().hex[:16], legacy['offer_id']),
            )

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

    def count_videos_since(self, profile_id: str, since_iso: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS total FROM videos
            WHERE COALESCE(profile_id, 'default') = ? AND created_at >= ?
            """,
            (profile_id, since_iso),
        ).fetchone()
        return int(row['total'] if row else 0)

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
                data.get('cta', '').strip() or 'Перевір посилання в профілі',
                data.get('disclosure', '').strip()
                or 'Партнерське посилання: я можу отримати комісію без доплати з вашого боку.',
                now,
                now,
            ),
        )
        self.conn.execute(
            """UPDATE affiliate_offers SET advertiser_name = ?, campaign_type = ?,
               payout_model = ?, payout_value = ?, currency = ?, budget_total = ?,
               starts_at = ?, ends_at = ?, tracking_slug = ?, approved_claims = ?,
               prohibited_claims = ? WHERE offer_id = ?""",
            (
                data.get('advertiser_name', '').strip() or data['name'].strip(),
                data.get('campaign_type', 'affiliate').strip().lower(),
                data.get('payout_model', 'CPS').strip().upper(),
                float(data.get('payout_value') or 0),
                data.get('currency', 'USD').strip().upper()[:3],
                float(data.get('budget_total') or 0),
                data.get('starts_at') or None,
                data.get('ends_at') or None,
                uuid.uuid4().hex[:16],
                data.get('approved_claims', '').strip(),
                data.get('prohibited_claims', '').strip(),
                offer_id,
            ),
        )
        self.conn.commit()
        return self.get_affiliate_offer(offer_id) or {}

    def list_affiliate_offers(
        self, profile_id: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[Dict]:
        status_clause = "" if include_inactive else "AND status = 'active'"
        if profile_id:
            rows = self.conn.execute(
                """SELECT * FROM affiliate_offers
                   WHERE enabled = 1 AND profile_id = ? """ + status_clause
                + " ORDER BY created_at DESC",
                (profile_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM affiliate_offers WHERE enabled = 1 " + status_clause
                + " ORDER BY created_at DESC"
            ).fetchall()
        return [self._offer_row(row) for row in rows]

    def get_affiliate_offer(self, offer_id: str) -> Optional[Dict]:
        row = self.conn.execute(
            """SELECT * FROM affiliate_offers
               WHERE offer_id = ? AND enabled = 1 AND status = 'active'""",
            (offer_id,),
        ).fetchone()
        return self._offer_row(row) if row else None

    def get_campaign(self, offer_id: str) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM affiliate_offers WHERE offer_id = ? AND enabled = 1",
            (offer_id,),
        ).fetchone()
        return self._offer_row(row) if row else None

    def get_campaign_by_slug(self, tracking_slug: str) -> Optional[Dict]:
        row = self.conn.execute(
            """SELECT * FROM affiliate_offers
               WHERE tracking_slug = ? AND enabled = 1 AND status = 'active'""",
            (tracking_slug,),
        ).fetchone()
        return self._offer_row(row) if row else None

    def update_campaign_status(self, offer_id: str, status: str) -> Dict:
        if status not in {'draft', 'active', 'paused', 'ended'}:
            raise ValueError('Невідомий статус кампанії')
        cursor = self.conn.execute(
            "UPDATE affiliate_offers SET status = ?, updated_at = ? WHERE offer_id = ?",
            (status, datetime.now(timezone.utc).isoformat(), offer_id),
        )
        if cursor.rowcount != 1:
            raise ValueError('Кампанію не знайдено')
        self.conn.commit()
        return self.get_campaign(offer_id) or {}

    def select_best_affiliate_offer(
        self, profile_id: str, niche_id: Optional[str] = None
    ) -> Optional[Dict]:
        """Choose an enabled offer using confirmed EPC plus controlled exploration."""
        offers = self.list_affiliate_offers(profile_id)
        if not offers:
            return None

        try:
            prior_clicks = max(
                1.0, float(os.getenv('AFFILIATE_PRIOR_CLICKS', '8'))
            )
        except (TypeError, ValueError):
            prior_clicks = 8.0
        try:
            prior_epc = max(
                0.0, float(os.getenv('AFFILIATE_PRIOR_EPC', '0.25'))
            )
        except (TypeError, ValueError):
            prior_epc = 0.25
        try:
            exploration = max(
                0.0, float(os.getenv('AFFILIATE_EXPLORATION_FACTOR', '0.15'))
            )
        except (TypeError, ValueError):
            exploration = 0.15

        total_clicks = 0
        candidates = []
        niche_text = str(niche_id or '').strip().lower()
        for offer in offers:
            stats = self.get_affiliate_stats(
                profile_id=profile_id, offer_id=offer['offer_id']
            )
            clicks = int(stats.get('clicks', 0) or 0)
            revenue = float(stats.get('revenue', 0) or 0)
            total_clicks += clicks
            keywords = [str(item).lower() for item in offer.get('keywords', [])]
            niche_match = bool(
                niche_text and any(
                    niche_text in keyword or keyword in niche_text
                    for keyword in keywords
                )
            )
            smoothed_epc = (
                revenue + prior_epc * prior_clicks
            ) / (clicks + prior_clicks)
            exploration_bonus = exploration * math.sqrt(
                math.log(total_clicks + 2) / (clicks + 1)
            )
            niche_bonus = smoothed_epc * 0.10 if niche_match else 0.0
            candidates.append({
                'offer': offer,
                'clicks': clicks,
                'revenue': revenue,
                'score': smoothed_epc + exploration_bonus + niche_bonus,
            })

        selected = max(
            candidates,
            key=lambda item: (item['score'], item['revenue'], item['clicks'])
        )
        logger.info(
            "Affiliate offer selected: %s (score=%.4f, clicks=%s, revenue=%.4f)",
            selected['offer'].get('offer_id'),
            selected['score'],
            selected['clicks'],
            selected['revenue'],
        )
        return selected['offer']

    def record_affiliate_click(self, offer_id: str, data: Optional[Dict] = None) -> Dict:
        values = data or {}
        click_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO affiliate_clicks (
                click_id, offer_id, video_id, platform, sub_id, referrer,
                user_agent, ip_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                click_id,
                offer_id,
                values.get('video_id'),
                str(values.get('platform') or 'unknown')[:40],
                str(values.get('sub_id') or '')[:160],
                str(values.get('referrer') or '')[:500],
                str(values.get('user_agent') or '')[:500],
                str(values.get('ip_hash') or '')[:128],
                now,
            ),
        )
        self.conn.commit()
        return {
            'click_id': click_id,
            'offer_id': offer_id,
            'video_id': values.get('video_id'),
            'platform': str(values.get('platform') or 'unknown')[:40],
            'created_at': now,
        }

    def record_affiliate_conversion(self, offer_id: str, data: Dict) -> Dict:
        status = str(data.get('status') or 'approved').strip().lower()
        if status not in {'approved', 'pending', 'returned', 'rejected'}:
            raise ValueError('Невідомий статус конверсії')
        try:
            amount = float(data.get('amount', 0) or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError('Сума конверсії повинна бути числом') from exc
        if amount < 0:
            raise ValueError('Сума конверсії не може бути від’ємною')
        source = str(data.get('source') or 'manual').strip()[:40]
        order_id = str(data.get('order_id') or '').strip()[:160] or None
        now = datetime.now(timezone.utc).isoformat()
        occurred_at = str(data.get('occurred_at') or now)[:80]
        conversion_id = uuid.uuid4().hex
        existing = None
        if order_id:
            existing = self.conn.execute(
                "SELECT conversion_id FROM affiliate_conversions "
                "WHERE source = ? AND order_id = ?",
                (source, order_id),
            ).fetchone()
        if existing:
            conversion_id = existing['conversion_id']
            self.conn.execute(
                """
                UPDATE affiliate_conversions
                SET offer_id = ?, video_id = ?, platform = ?, amount = ?,
                    currency = ?, status = ?, occurred_at = ?
                WHERE conversion_id = ?
                """,
                (
                    offer_id,
                    data.get('video_id'),
                    str(data.get('platform') or 'unknown')[:40],
                    amount,
                    str(data.get('currency') or 'USD').upper()[:8],
                    status,
                    occurred_at,
                    conversion_id,
                ),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO affiliate_conversions (
                    conversion_id, offer_id, video_id, platform, order_id,
                    amount, currency, status, source, occurred_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversion_id,
                    offer_id,
                    data.get('video_id'),
                    str(data.get('platform') or 'unknown')[:40],
                    order_id,
                    amount,
                    str(data.get('currency') or 'USD').upper()[:8],
                    status,
                    source,
                    occurred_at,
                    now,
                ),
            )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM affiliate_conversions WHERE conversion_id = ?",
            (conversion_id,),
        ).fetchone()
        return dict(row) if row else {}

    def get_affiliate_stats(
        self,
        profile_id: Optional[str] = None,
        video_id: Optional[str] = None,
        offer_id: Optional[str] = None,
        since: Optional[str] = None,
    ) -> Dict:
        where = []
        params = []
        if profile_id:
            where.append(
                "offer_id IN (SELECT offer_id FROM affiliate_offers WHERE profile_id = ?)"
            )
            params.append(profile_id)
        if video_id:
            where.append("video_id = ?")
            params.append(video_id)
        if offer_id:
            where.append("offer_id = ?")
            params.append(offer_id)
        if since:
            where.append("created_at >= ?")
            params.append(since)
        predicate = f" WHERE {' AND '.join(where)}" if where else ''

        click_row = self.conn.execute(
            f"SELECT COUNT(*) AS total FROM affiliate_clicks{predicate}",
            params,
        ).fetchone()
        conversion_predicate = predicate.replace('created_at', 'occurred_at')
        conversion_row = self.conn.execute(
            f"""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved,
                   SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                   SUM(CASE WHEN status = 'approved' THEN amount ELSE 0 END) AS revenue,
                   SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END) AS pending_revenue
            FROM affiliate_conversions{conversion_predicate}
            """,
            params,
        ).fetchone()
        click_values = dict(click_row) if click_row else {}
        conversion_values = dict(conversion_row) if conversion_row else {}
        clicks = int(click_values.get('total', 0) or 0)
        conversions = int(conversion_values.get('total', 0) or 0)
        approved = int(conversion_values.get('approved', 0) or 0)
        revenue = float(conversion_values.get('revenue', 0) or 0)
        pending_revenue = float(conversion_values.get('pending_revenue', 0) or 0)
        return {
            'clicks': clicks,
            'conversions': conversions,
            'approved_conversions': approved,
            'pending_conversions': int(conversion_values.get('pending', 0) or 0),
            'revenue': round(revenue, 4),
            'pending_revenue': round(pending_revenue, 4),
            'conversion_rate': round(approved / clicks * 100, 3) if clicks else 0,
            'epc': round(revenue / clicks, 4) if clicks else 0,
        }

    @staticmethod
    def _offer_row(row: sqlite3.Row) -> Dict:
        offer = dict(row)
        try:
            offer['keywords'] = json.loads(offer.get('keywords') or '[]')
        except json.JSONDecodeError:
            offer['keywords'] = []
        offer['enabled'] = bool(offer.get('enabled'))
        base_url = os.getenv('PUBLIC_BASE_URL', '').strip().rstrip('/')
        offer['tracking_url'] = (
            f"{base_url}/go/{offer['tracking_slug']}"
            if base_url.startswith('https://') and offer.get('tracking_slug')
            else offer.get('url')
        )
        return offer

    def record_ad_event(
        self, offer_id: str, event_type: str, amount: float = 0,
        currency: str = 'USD', video_id: Optional[str] = None,
        source: str = 'manual', external_ref: Optional[str] = None,
        referrer_host: Optional[str] = None,
    ) -> int:
        if event_type not in {'click', 'conversion', 'revenue', 'refund'}:
            raise ValueError('Невідомий тип рекламної події')
        if not self.get_campaign(offer_id):
            raise ValueError('Кампанію не знайдено')
        cursor = self.conn.execute(
            """INSERT INTO ad_events (
                offer_id, video_id, event_type, amount, currency,
                source, external_ref, referrer_host, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                offer_id, video_id, event_type, float(amount or 0),
                str(currency or 'USD').upper()[:3], str(source or 'manual')[:40],
                external_ref, (referrer_host or '')[:255],
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def get_ad_center_summary(self, profile_id: Optional[str] = None) -> Dict:
        where = "WHERE o.enabled = 1"
        params: List = []
        if profile_id:
            where += " AND o.profile_id = ?"
            params.append(profile_id)
        rows = self.conn.execute(
            f"""SELECT o.offer_id, o.name, o.advertiser_name, o.profile_id,
                   o.campaign_type, o.status, o.payout_model, o.payout_value,
                   o.currency, o.budget_total, o.tracking_slug,
                   COUNT(CASE WHEN e.event_type = 'click' THEN 1 END) AS clicks,
                   COUNT(CASE WHEN e.event_type = 'conversion' THEN 1 END) AS conversions,
                   COALESCE(SUM(CASE
                     WHEN e.event_type IN ('conversion', 'revenue') THEN e.amount
                     WHEN e.event_type = 'refund' THEN -ABS(e.amount)
                     ELSE 0 END), 0) AS revenue
                FROM affiliate_offers o
                LEFT JOIN ad_events e ON e.offer_id = o.offer_id
                {where}
                GROUP BY o.offer_id
                ORDER BY revenue DESC, clicks DESC, o.created_at DESC""",
            params,
        ).fetchall()
        campaigns = []
        for row in rows:
            item = dict(row)
            clicks = int(item.get('clicks') or 0)
            conversions = int(item.get('conversions') or 0)
            revenue = float(item.get('revenue') or 0)
            item['epc'] = round(revenue / clicks, 4) if clicks else 0
            item['conversion_rate'] = round(conversions / clicks * 100, 2) if clicks else 0
            campaigns.append(item)
        total_clicks = sum(int(item['clicks']) for item in campaigns)
        total_conversions = sum(int(item['conversions']) for item in campaigns)
        total_revenue = sum(float(item['revenue']) for item in campaigns)
        currencies = {item['currency'] for item in campaigns if item.get('currency')}
        return {
            'campaigns': campaigns,
            'totals': {
                'campaigns': len(campaigns),
                'active_campaigns': sum(item['status'] == 'active' for item in campaigns),
                'clicks': total_clicks,
                'conversions': total_conversions,
                'revenue': round(total_revenue, 2),
                'currency': next(iter(currencies)) if len(currencies) == 1 else ('MIXED' if currencies else 'USD'),
                'epc': round(total_revenue / total_clicks, 4) if total_clicks else 0,
                'conversion_rate': round(total_conversions / total_clicks * 100, 2) if total_clicks else 0,
            },
        }

    def create_advertiser_lead(self, data: Dict) -> Dict:
        lead_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO advertiser_leads (
                lead_id, contact_name, email, company, website, budget,
                currency, objective, notes, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)""",
            (
                lead_id, data['contact_name'], data['email'], data['company'],
                data.get('website'), float(data.get('budget') or 0),
                str(data.get('currency') or 'USD').upper()[:3],
                data.get('objective'), data.get('notes'), now, now,
            ),
        )
        self.conn.commit()
        return self.get_advertiser_lead(lead_id) or {}

    def get_advertiser_lead(self, lead_id: str) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM advertiser_leads WHERE lead_id = ?", (lead_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_advertiser_leads(self, limit: int = 100) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM advertiser_leads ORDER BY created_at DESC LIMIT ?",
            (max(1, min(int(limit), 200)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def update_advertiser_lead_status(self, lead_id: str, status: str) -> Dict:
        if status not in {'new', 'contacted', 'approved', 'rejected'}:
            raise ValueError('Невідомий статус заявки')
        cursor = self.conn.execute(
            "UPDATE advertiser_leads SET status = ?, updated_at = ? WHERE lead_id = ?",
            (status, datetime.now(timezone.utc).isoformat(), lead_id),
        )
        if cursor.rowcount != 1:
            raise ValueError('Заявку не знайдено')
        self.conn.commit()
        return self.get_advertiser_lead(lead_id) or {}

    # ------------------------------------------------------------------
    # Single-administrator security
    # ------------------------------------------------------------------

    def get_admin(self) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM admin_users WHERE admin_id = 1"
        ).fetchone()
        return dict(row) if row else None

    def create_admin(self, email: str, password_hash: str) -> Dict:
        if self.get_admin():
            raise ValueError('Адміністратор уже створений')
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO admin_users (
                admin_id, email, password_hash, created_at, updated_at
            ) VALUES (1, ?, ?, ?, ?)
            """,
            (email.strip().lower(), password_hash, now, now),
        )
        self.conn.commit()
        return self.get_admin() or {}

    def update_admin_login(self) -> None:
        self.conn.execute(
            "UPDATE admin_users SET last_login_at = ? WHERE admin_id = 1",
            (datetime.now(timezone.utc).isoformat(),),
        )
        self.conn.commit()

    def update_admin_password(self, password_hash: str) -> None:
        cursor = self.conn.execute(
            """
            UPDATE admin_users SET password_hash = ?, updated_at = ?
            WHERE admin_id = 1
            """,
            (password_hash, datetime.now(timezone.utc).isoformat()),
        )
        if cursor.rowcount != 1:
            raise ValueError('Адміністратор не налаштований')
        # Changing a password invalidates every outstanding reset link.
        self.conn.execute(
            """
            UPDATE password_reset_tokens SET used_at = ?
            WHERE admin_id = 1 AND used_at IS NULL
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )
        self.conn.commit()

    def create_password_reset_token(
        self, token_hash: str, expires_at: str
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            UPDATE password_reset_tokens SET used_at = ?
            WHERE admin_id = 1 AND used_at IS NULL
            """,
            (now,),
        )
        self.conn.execute(
            """
            INSERT INTO password_reset_tokens (
                admin_id, token_hash, expires_at, created_at
            ) VALUES (1, ?, ?, ?)
            """,
            (token_hash, expires_at, now),
        )
        self.conn.commit()

    def get_valid_password_reset(self, token_hash: str) -> Optional[Dict]:
        now = datetime.now(timezone.utc).isoformat()
        row = self.conn.execute(
            """
            SELECT * FROM password_reset_tokens
            WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?
            ORDER BY token_id DESC LIMIT 1
            """,
            (token_hash, now),
        ).fetchone()
        return dict(row) if row else None

    def mark_password_reset_used(self, token_hash: str) -> None:
        self.conn.execute(
            """
            UPDATE password_reset_tokens SET used_at = ?
            WHERE token_hash = ? AND used_at IS NULL
            """,
            (datetime.now(timezone.utc).isoformat(), token_hash),
        )
        self.conn.commit()

    def log_audit(
        self,
        action: str,
        details: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        admin_id: Optional[int] = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO audit_log (
                admin_id, action, details, ip_address, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                admin_id,
                action[:120],
                json.dumps(details or {}, ensure_ascii=False),
                (ip_address or '')[:100],
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    def list_audit(self, limit: int = 50) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?",
            (max(1, min(limit, 200)),),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item['details'] = json.loads(item.get('details') or '{}')
            except json.JSONDecodeError:
                item['details'] = {}
            result.append(item)
        return result

    # ------------------------------------------------------------------
    # Official automation bot run log
    # ------------------------------------------------------------------

    def start_automation_run(
        self,
        run_id: str,
        trigger_source: str,
        profile_id: str,
        content_mode: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO automation_runs (
                run_id, trigger_source, profile_id, content_mode,
                status, created_at
            ) VALUES (?, ?, ?, ?, 'queued', ?)
            """,
            (
                run_id,
                trigger_source[:40],
                profile_id,
                content_mode,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    def finish_automation_run(
        self, run_id: str, status: str, message: str = ''
    ) -> None:
        self.conn.execute(
            """
            UPDATE automation_runs
            SET status = ?, message = ?, completed_at = ?
            WHERE run_id = ?
            """,
            (
                status[:20],
                message[:1000],
                datetime.now(timezone.utc).isoformat(),
                run_id,
            ),
        )
        self.conn.commit()

    def list_automation_runs(self, limit: int = 30) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM automation_runs ORDER BY created_at DESC LIMIT ?",
            (max(1, min(limit, 100)),),
        ).fetchall()
        return [dict(row) for row in rows]

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
