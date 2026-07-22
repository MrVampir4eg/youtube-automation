"""
Main Orchestrator
Головний модуль який об'єднує всі компоненти системи
"""

import os
import logging
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
import json
import uuid

from src.content_generator import ContentGenerator
from src.voice_synthesizer import VoiceSynthesizer
from src.video_renderer import VideoRenderer
from src.youtube_uploader import YouTubeUploader
from database.models import Database, Video

logger = logging.getLogger(__name__)


class VideoProducer:
    """Головний оркестратор для створення та публікації відео"""

    def __init__(self):
        self.content_gen = ContentGenerator()
        self.voice_synth = VoiceSynthesizer()
        self.video_render = VideoRenderer()
        self.youtube = YouTubeUploader()
        self.db = Database()

        # Статистика сесії
        self.session_stats = {
            'videos_created': 0,
            'videos_uploaded': 0,
            'total_cost': 0.0,
            'errors': []
        }

    def produce_video(self,
                     niche_id: Optional[str] = None,
                     auto_upload: bool = None) -> Dict:
        """
        Повний цикл створення відео: генерація → озвучка → рендеринг → публікація

        Args:
            niche_id: ID ніші (якщо None - випадкова)
            auto_upload: Чи завантажувати автоматично (якщо None - з .env)

        Returns:
            {
                'video_id': str,
                'video_path': Path,
                'youtube_url': str (якщо uploaded),
                'stats': {...}
            }
        """

        video_id = str(uuid.uuid4())[:8]
        logger.info(f"{'='*60}")
        logger.info(f"Starting video production: {video_id}")
        logger.info(f"{'='*60}")

        try:
            # 1. ГЕНЕРАЦІЯ СКРИПТУ
            logger.info("Step 1/5: Generating script...")
            script = self.content_gen.generate_script(niche_id=niche_id)

            logger.info(f"  Ніша: {script['niche_name']}")
            logger.info(f"  Тип: {script['template']}")
            logger.info(f"  Тривалість: {script['estimated_duration']}s")

            # 2. СИНТЕЗ ОЗВУЧКИ
            logger.info("Step 2/5: Synthesizing voice...")
            audio_result = self.voice_synth.synthesize(
                text=script['full_script'],
                niche=script['niche'],
                video_id=video_id
            )

            logger.info(f"  Аудіо: {audio_result['audio_path'].name}")
            logger.info(f"  Голос: {audio_result['voice_used']}")

            # 3. РЕНДЕРИНГ ВІДЕО
            logger.info("Step 3/5: Rendering video...")
            video_result = self.video_render.create_video(
                audio_path=audio_result['audio_path'],
                script_data=script,
                video_id=video_id
            )

            logger.info(f"  Відео: {video_result['video_path'].name}")
            logger.info(f"  Розмір: {video_result['filesize']/1024/1024:.1f}MB")

            # 4. ГЕНЕРАЦІЯ SEO МЕТАДАНИХ
            logger.info("Step 4/5: Generating SEO metadata...")
            seo = self.content_gen.generate_seo_metadata(script)

            logger.info(f"  Title: {seo['title'][:50]}...")
            logger.info(f"  Tags: {len(seo['tags'])} тегів")

            # 5. ЗАВАНТАЖЕННЯ НА YOUTUBE
            youtube_result = None
            if auto_upload is None:
                auto_upload = os.getenv('AUTO_UPLOAD', 'True').lower() == 'true'

            if auto_upload:
                logger.info("Step 5/5: Uploading to YouTube...")
                youtube_result = self.youtube.upload_video(
                    video_path=video_result['video_path'],
                    title=seo['title'],
                    description=seo['description'],
                    tags=seo['tags'],
                    category_id=seo['category_id']
                )

                logger.info(f"  URL: {youtube_result['url']}")
            else:
                logger.info("Step 5/5: Skipping upload (auto_upload=False)")

            # Збереження в БД
            video_data = {
                'video_id': video_id,
                'niche': script['niche'],
                'title': seo['title'],
                'description': seo['description'],
                'script': script['full_script'],
                'video_path': str(video_result['video_path']),
                'audio_path': str(audio_result['audio_path']),
                'duration': video_result['duration'],
                'filesize': video_result['filesize'],
                'youtube_video_id': youtube_result['video_id'] if youtube_result else None,
                'youtube_url': youtube_result['url'] if youtube_result else None,
                'created_at': datetime.utcnow().isoformat(),
                'ai_cost': script['metadata']['cost'] + (audio_result.get('cost', 0) or 0)
            }

            self.db.add_video(video_data)

            # Оновлення статистики
            self.session_stats['videos_created'] += 1
            if youtube_result:
                self.session_stats['videos_uploaded'] += 1
            self.session_stats['total_cost'] += video_data['ai_cost']

            logger.info(f"{'='*60}")
            logger.info(f"✓ VIDEO PRODUCTION COMPLETE: {video_id}")
            logger.info(f"{'='*60}")

            return {
                'video_id': video_id,
                'video_path': video_result['video_path'],
                'youtube_url': youtube_result['url'] if youtube_result else None,
                'youtube_video_id': youtube_result['video_id'] if youtube_result else None,
                'niche': script['niche'],
                'title': seo['title'],
                'duration': video_result['duration'],
                'stats': {
                    'render_time': video_result['render_time'],
                    'ai_cost': video_data['ai_cost'],
                    'filesize_mb': video_result['filesize'] / 1024 / 1024
                }
            }

        except Exception as e:
            logger.error(f"Production error: {e}")
            self.session_stats['errors'].append({
                'video_id': video_id,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            })
            raise

    def produce_batch(self, count: int, niches: Optional[list] = None) -> list:
        """
        Пакетне створення відео

        Args:
            count: Кількість відео
            niches: Список ніш (якщо None - random rotation)

        Returns:
            List of results
        """

        logger.info(f"Starting batch production: {count} videos")

        results = []
        niche_rotation = niches or list(self.content_gen.niches.keys())
        niche_index = 0

        for i in range(count):
            try:
                niche = niche_rotation[niche_index % len(niche_rotation)]
                logger.info(f"\n>>> Video {i+1}/{count} (Niche: {niche})")

                result = self.produce_video(niche_id=niche)
                results.append(result)

                niche_index += 1

            except Exception as e:
                logger.error(f"Failed to produce video {i+1}: {e}")
                results.append({
                    'error': str(e),
                    'video_index': i+1
                })

        logger.info(f"\n{'='*60}")
        logger.info(f"BATCH COMPLETE: {len(results)} videos")
        logger.info(f"Success: {sum(1 for r in results if 'error' not in r)}")
        logger.info(f"Failed: {sum(1 for r in results if 'error' in r)}")
        logger.info(f"{'='*60}")

        return results

    def get_session_stats(self) -> Dict:
        """Статистика поточної сесії"""
        return {
            **self.session_stats,
            'ai_stats': self.content_gen.get_daily_stats(),
            'voice_stats': self.voice_synth.get_usage_stats(),
            'youtube_quota': self.youtube.get_quota_usage()
        }

    def get_video_performance(self, video_id: str) -> Dict:
        """Отримання перформансу відео"""
        video = self.db.get_video(video_id)

        if not video or not video.get('youtube_video_id'):
            return {'error': 'Video not found or not uploaded'}

        # Отримуємо stats з YouTube
        analytics = self.youtube.get_video_analytics(video['youtube_video_id'])

        # Розраховуємо ROI
        ai_cost = video.get('ai_cost', 0)
        views = analytics.get('views', 0)

        # Приблизний розрахунок доходу (CPM $0.05-0.10 для Shorts)
        estimated_revenue = (views / 1000) * 0.075  # Середній $0.075 CPM

        return {
            'video_id': video_id,
            'youtube_video_id': video['youtube_video_id'],
            'title': video['title'],
            'niche': video['niche'],
            'created_at': video['created_at'],
            'analytics': analytics,
            'financials': {
                'ai_cost': ai_cost,
                'estimated_revenue': round(estimated_revenue, 4),
                'roi': round((estimated_revenue / ai_cost - 1) * 100, 1) if ai_cost > 0 else 0,
                'profit': round(estimated_revenue - ai_cost, 4)
            }
        }

    def get_top_performing_videos(self, limit: int = 10) -> list:
        """Топ відео по переглядам"""
        videos = self.db.list_videos(limit=100)

        # Отримуємо analytics для кожного
        with_analytics = []
        for video in videos:
            if video.get('youtube_video_id'):
                analytics = self.youtube.get_video_analytics(video['youtube_video_id'])
                video['analytics'] = analytics
                with_analytics.append(video)

        # Сортуємо по переглядам
        sorted_videos = sorted(
            with_analytics,
            key=lambda x: x.get('analytics', {}).get('views', 0),
            reverse=True
        )

        return sorted_videos[:limit]

    def cleanup_old_files(self, days: int = 7):
        """Очистка старих файлів"""
        logger.info(f"Cleaning up files older than {days} days...")

        # Аудіо
        audio_cleaned = self.voice_synth.cleanup_old_audio(days)

        # Відео (опційно, якщо хочете видаляти локальні файли)
        # video_cleaned = self._cleanup_videos(days)

        logger.info(f"✓ Cleanup complete: {audio_cleaned} audio files removed")


if __name__ == '__main__':
    # Тестування
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )

    producer = VideoProducer()

    print("\n" + "="*60)
    print("YouTube Shorts Automation System - Test Run")
    print("="*60)

    # Створюємо одне тестове відео
    print("\nCreating test video...")

    result = producer.produce_video(
        niche_id='motivation',
        auto_upload=False  # Не завантажуємо для тесту
    )

    print("\n" + "="*60)
    print("✓ TEST COMPLETE")
    print("="*60)
    print(f"\nVideo ID: {result['video_id']}")
    print(f"Path: {result['video_path']}")
    print(f"Duration: {result['duration']:.1f}s")
    print(f"Render time: {result['stats']['render_time']:.1f}s")
    print(f"AI cost: ${result['stats']['ai_cost']:.4f}")
    print(f"File size: {result['stats']['filesize_mb']:.1f}MB")

    # Статистика
    stats = producer.get_session_stats()
    print(f"\n📊 Session Stats:")
    print(f"  Videos created: {stats['videos_created']}")
    print(f"  Total AI cost: ${stats['total_cost']:.4f}")
    print(f"  AI tokens: {stats['ai_stats']['tokens_used']}")
    print(f"  Voice chars: {stats['voice_stats']['chars_used']}")
