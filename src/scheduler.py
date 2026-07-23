"""
Scheduler
Автоматична генерація та публікація відео по розкладу
"""

import os
import logging
from datetime import datetime, time
from typing import Optional
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.orchestrator import VideoProducer
from database.models import Database

logger = logging.getLogger(__name__)


class AutomationScheduler:
    """Планувальник автоматичної генерації відео"""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.producer = VideoProducer()
        self.db = Database()

        # Налаштування з .env
        self.timezone = pytz.timezone(os.getenv('TIMEZONE', 'Europe/Kyiv'))
        self.videos_per_day = int(os.getenv('VIDEOS_PER_DAY', 3))
        self.generation_time = int(os.getenv('GENERATION_TIME', 3))  # Година дня
        self.internal_generation_enabled = os.getenv(
            'ENABLE_INTERNAL_SCHEDULER', 'False'
        ).lower() == 'true'

        self.is_running = False

    def start(self):
        """Запуск scheduler"""
        if self.is_running:
            logger.warning("Scheduler already running")
            return

        logger.info("Starting automation scheduler...")

        # На Render Free надійніший зовнішній GitHub Actions schedule. Старий
        # внутрішній batch можна ввімкнути окремо, але за замовчуванням він не
        # створює дублікати поверх чотирьох market-слотів.
        if self.internal_generation_enabled and self.videos_per_day > 0:
            self.scheduler.add_job(
                self.daily_video_generation,
                trigger=CronTrigger(
                    hour=self.generation_time,
                    minute=0,
                    timezone=self.timezone
                ),
                id='daily_generation',
                name='Daily Video Generation',
                replace_existing=True
            )
        else:
            logger.info('Internal generation disabled; using external schedule')

        # Оновлення аналітики кожні 6 годин
        self.scheduler.add_job(
            self.update_analytics,
            trigger=CronTrigger(
                hour='*/6',
                timezone=self.timezone
            ),
            id='analytics_update',
            name='Analytics Update',
            replace_existing=True
        )

        # Оновлення денної статистики о północі
        self.scheduler.add_job(
            self.update_daily_stats,
            trigger=CronTrigger(
                hour=0,
                minute=5,
                timezone=self.timezone
            ),
            id='daily_stats',
            name='Daily Stats Update',
            replace_existing=True
        )

        # Cleanup старих файлів щотижня
        self.scheduler.add_job(
            self.weekly_cleanup,
            trigger=CronTrigger(
                day_of_week='sun',
                hour=2,
                timezone=self.timezone
            ),
            id='weekly_cleanup',
            name='Weekly Cleanup',
            replace_existing=True
        )

        self.scheduler.start()
        self.is_running = True

        logger.info("✓ Scheduler started")
        self._print_schedule()

    def stop(self):
        """Зупинка scheduler"""
        if not self.is_running:
            return

        self.scheduler.shutdown()
        self.is_running = False
        logger.info("Scheduler stopped")

    def daily_video_generation(self):
        """Щоденна генерація відео"""
        logger.info(f"{'='*60}")
        logger.info(f"DAILY VIDEO GENERATION STARTED")
        logger.info(f"Target: {self.videos_per_day} videos")
        logger.info(f"{'='*60}")

        try:
            # Генерація відео
            results = self.producer.produce_batch(
                count=self.videos_per_day,
                trigger_source='internal_scheduler',
            )

            # Підрахунок успішних
            successful = sum(1 for r in results if 'error' not in r)
            failed = len(results) - successful

            logger.info(f"{'='*60}")
            logger.info(f"DAILY GENERATION COMPLETE")
            logger.info(f"Success: {successful}/{self.videos_per_day}")
            logger.info(f"Failed: {failed}")
            logger.info(f"{'='*60}")

            # Логування в БД якщо були помилки
            if failed > 0:
                for result in results:
                    if 'error' in result:
                        self.db.log_error(
                            video_id=None,
                            error_type='generation_error',
                            error_message=result['error'],
                            stack_trace=None
                        )

        except Exception as e:
            logger.error(f"Daily generation failed: {e}")
            self.db.log_error(
                video_id=None,
                error_type='scheduler_error',
                error_message=str(e),
                stack_trace=None
            )

    def update_analytics(self):
        """Оновлення аналітики всіх відео"""
        logger.info("Updating analytics for all videos...")

        try:
            # Отримуємо всі відео з YouTube IDs
            videos = self.db.list_videos(limit=100)
            updated = 0

            for video in videos:
                if video.get('youtube_video_id'):
                    try:
                        uploader = self.producer.get_youtube_uploader(
                            video.get('profile_id') or 'default'
                        )
                        analytics = uploader.get_video_analytics(
                            video['youtube_video_id']
                        )

                        if analytics:
                            self.db.update_analytics(
                                video['video_id'],
                                video['youtube_video_id'],
                                analytics
                            )
                            updated += 1

                    except Exception as e:
                        logger.error(f"Failed to update analytics for {video['video_id']}: {e}")

            logger.info(f"✓ Analytics updated: {updated} videos")

        except Exception as e:
            logger.error(f"Analytics update failed: {e}")

    def update_daily_stats(self):
        """Оновлення денної статистики"""
        logger.info("Updating daily stats...")

        try:
            today = datetime.now(self.timezone).date().isoformat()

            # Отримуємо відео за сьогодні
            videos_today = [
                v for v in self.db.list_videos(limit=100)
                if v['created_at'].startswith(today)
            ]

            videos_created = len(videos_today)
            videos_uploaded = sum(1 for v in videos_today if v.get('youtube_video_id'))

            # Підрахунок переглядів та доходу
            total_views = 0
            total_cost = sum(v.get('ai_cost', 0) for v in videos_today)

            for video in videos_today:
                if video.get('youtube_video_id'):
                    analytics = self.db.get_latest_analytics(video['video_id'])
                    if analytics:
                        total_views += analytics.get('views', 0)

            # Оцінка доходу (CPM $0.075)
            try:
                shorts_rpm = max(
                    0.0, float(os.getenv('SHORTS_RPM_ESTIMATE', '0.075'))
                )
            except ValueError:
                shorts_rpm = 0.075
            shorts_revenue = (total_views / 1000) * shorts_rpm
            affiliate_stats = self.db.get_affiliate_stats(since=today)
            affiliate_revenue = affiliate_stats.get('revenue', 0)
            total_revenue = shorts_revenue + affiliate_revenue
            profit = total_revenue - total_cost

            stats = {
                'videos_created': videos_created,
                'videos_uploaded': videos_uploaded,
                'total_views': total_views,
                'shorts_revenue_estimate': round(shorts_revenue, 4),
                'affiliate_revenue': round(affiliate_revenue, 4),
                'total_revenue': round(total_revenue, 4),
                'total_cost': round(total_cost, 4),
                'profit': round(profit, 4)
            }

            self.db.update_daily_stats(today, stats)

            logger.info(f"✓ Daily stats updated:")
            logger.info(f"  Created: {videos_created}")
            logger.info(f"  Uploaded: {videos_uploaded}")
            logger.info(f"  Views: {total_views}")
            logger.info(f"  Revenue: ${total_revenue:.2f}")
            logger.info(f"  Cost: ${total_cost:.2f}")
            logger.info(f"  Profit: ${profit:.2f}")

        except Exception as e:
            logger.error(f"Daily stats update failed: {e}")

    def weekly_cleanup(self):
        """Щотижнева очистка старих файлів"""
        logger.info("Running weekly cleanup...")

        try:
            self.producer.cleanup_old_files(days=7)
            logger.info("✓ Weekly cleanup complete")

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

    def trigger_manual_generation(
        self,
        count: int = 1,
        niche: Optional[str] = None,
        content_mode: str = 'organic',
        profile_id: str = 'default',
        affiliate_offer_id: Optional[str] = None,
        publish_scope: str = 'all_enabled',
        trigger_source: str = 'manual',
    ):
        """Ручний запуск генерації"""
        logger.info(f"Manual generation triggered: {count} videos")

        try:
            results = [
                self.producer.produce_video(
                    niche_id=niche,
                    content_mode=content_mode,
                    profile_id=profile_id,
                    affiliate_offer_id=affiliate_offer_id,
                    publish_scope=publish_scope,
                    trigger_source=trigger_source,
                )
                for _ in range(count)
            ]

            return results

        except Exception as e:
            logger.error(f"Manual generation failed: {e}")
            raise

    def get_next_run_times(self) -> dict:
        """Час наступних запусків"""
        jobs = {}

        for job in self.scheduler.get_jobs():
            jobs[job.name] = {
                'id': job.id,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None
            }

        return jobs

    def _print_schedule(self):
        """Вивести розклад"""
        logger.info("\n📅 Scheduled Jobs:")

        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else 'N/A'
            logger.info(f"  • {job.name}: {next_run}")


if __name__ == '__main__':
    # Тестування
    from dotenv import load_dotenv
    import time

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    scheduler = AutomationScheduler()

    print("\n" + "="*60)
    print("Testing Automation Scheduler")
    print("="*60)

    # Запуск
    scheduler.start()

    # Показати розклад
    schedule = scheduler.get_next_run_times()
    print("\n📅 Next Scheduled Runs:")
    for name, info in schedule.items():
        print(f"  • {name}: {info['next_run']}")

    # Тестовий manual trigger
    print("\n🚀 Triggering manual generation...")
    try:
        result = scheduler.trigger_manual_generation(count=1, niche='motivation')
        print(f"✓ Generated: {result[0]['video_id']}")
    except Exception as e:
        print(f"✗ Error: {e}")

    print("\n⏸ Scheduler running... (Press Ctrl+C to stop)")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopping scheduler...")
        scheduler.stop()
        print("✓ Stopped")
