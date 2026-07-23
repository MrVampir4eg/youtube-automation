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

from src.video_renderer import VideoRenderer
from src.youtube_uploader import YouTubeUploader
from src.platform_publishers import (
    UniversalPublisher, build_platform_metadata, enabled_platforms
)
from src.policy_guard import MonetizationPolicyGuard
from database.models import Database, Video

logger = logging.getLogger(__name__)


class VideoProducer:
    """Головний оркестратор для створення та публікації відео"""

    def __init__(self):
        # Якщо вказано Groq або USE_FREE_MODE, не вимагаємо
        # OpenAI/ElevenLabs і використовуємо безкоштовні компоненти.
        use_free_mode = (
            os.getenv('USE_FREE_MODE', 'False').lower() == 'true'
            or (bool(os.getenv('GROQ_API_KEY')) and not os.getenv('OPENAI_API_KEY'))
        )

        if use_free_mode:
            from src.free_content_generator import FreeContentGenerator
            from src.free_voice_synthesizer import FreeVoiceSynthesizer

            self.content_gen = FreeContentGenerator()
            self.voice_synth = FreeVoiceSynthesizer()
            logger.info("✓ Free mode enabled: Groq/fallback + gTTS")
        else:
            # Платні SDK імпортуємо лише коли вони справді потрібні.
            # Це не дає несумісному ElevenLabs SDK зламати free mode.
            from src.content_generator import ContentGenerator
            from src.voice_synthesizer import VoiceSynthesizer

            self.content_gen = ContentGenerator()
            self.voice_synth = VoiceSynthesizer()

        self.video_render = VideoRenderer()
        self.youtube = YouTubeUploader()
        self.publisher = UniversalPublisher(self.youtube)
        self.db = Database()
        self.policy_guard = MonetizationPolicyGuard(self.db)

        # Статистика сесії
        self.session_stats = {
            'videos_created': 0,
            'videos_uploaded': 0,
            'platform_uploads': {},
            'total_cost': 0.0,
            'errors': []
        }

    def produce_video(self,
                     niche_id: Optional[str] = None,
                     auto_upload: bool = None,
                     content_mode: str = 'organic',
                     profile_id: str = 'default',
                     affiliate_offer_id: Optional[str] = None,
                     publish_scope: str = 'all_enabled',
                     trigger_source: str = 'manual') -> Dict:
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

        content_mode = (
            content_mode if content_mode in {'organic', 'affiliate'} else 'organic'
        )
        if publish_scope not in {'create_only', 'youtube_only', 'all_enabled'}:
            raise ValueError('Невідомий режим публікації')
        profile = self.db.get_channel_profile(profile_id, include_secrets=True)
        if not profile:
            raise ValueError('Вибраний профіль каналу не знайдено')
        offer = None
        if content_mode == 'affiliate':
            auto_offer_requested = str(affiliate_offer_id or '').lower() == 'auto'
            if auto_offer_requested:
                if os.getenv('AUTO_SELECT_AFFILIATE_OFFER', 'False').lower() == 'true':
                    offer = self.db.select_best_affiliate_offer(
                        profile_id, niche_id=niche_id
                    )
                    affiliate_offer_id = offer.get('offer_id') if offer else None
                    if not offer:
                        logger.warning(
                            'No enabled affiliate offer found; falling back to organic content'
                        )
                        content_mode = 'organic'
            if not affiliate_offer_id:
                if content_mode == 'affiliate':
                    raise ValueError(
                        'Для партнерського режиму немає дозволеної affiliate offer'
                    )
            else:
                offer = offer or self.db.get_affiliate_offer(affiliate_offer_id)
                if not offer or offer.get('profile_id') != profile_id:
                    raise ValueError('Партнерська пропозиція не належить цьому каналу')
        if trigger_source not in {'manual', 'manual_admin'}:
            self.policy_guard.validate_automated_frequency(profile_id)

        video_id = str(uuid.uuid4())[:8]
        logger.info(f"{'='*60}")
        logger.info(f"Starting video production: {video_id}")
        logger.info(f"{'='*60}")

        try:
            # 1. ГЕНЕРАЦІЯ СКРИПТУ
            logger.info("Step 1/5: Generating script...")
            script = self.content_gen.generate_script(
                niche_id=niche_id,
                content_mode=content_mode,
                affiliate_offer=offer,
                channel_name=profile.get('youtube_channel_title') or profile['name'],
            )
            # All rendered videos use synthetic narration and/or generated
            # creative assistance. A conservative disclosure is safer and does
            # not itself make content ineligible for monetization.
            script.setdefault('metadata', {})['contains_synthetic_media'] = True
            self.policy_guard.validate_script(script, content_mode, offer)

            logger.info(f"  Ніша: {script['niche_name']}")
            logger.info(
                f"  Якість сценарію: {script.get('quality_score', 'n/a')}/100"
            )
            logger.info(f"  Тема: {script.get('topic', script['niche_name'])}")
            logger.info(
                f"  Тип: {script.get('template', script['metadata'].get('provider', 'default'))}"
            )
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

            # Edge TTS повертає точні межі слів. Renderer використовує їх для
            # коротких синхронних caption-блоків; gTTS працює через fallback.
            script['word_timings'] = audio_result.get('word_timings', [])
            script['estimated_duration'] = audio_result.get(
                'duration', script['estimated_duration']
            )

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
            if offer and seo.get('affiliate'):
                seo['affiliate'].update({
                    'offer_id': offer.get('offer_id') or affiliate_offer_id,
                    'video_id': video_id,
                    'tracking_base_url': (
                        os.getenv('PUBLIC_BASE_URL', '').strip().rstrip('/')
                    ),
                })
            self.policy_guard.validate_metadata(seo, content_mode)

            logger.info(f"  Title: {seo['title'][:50]}...")
            logger.info(f"  Tags: {len(seo['tags'])} тегів")

            # 5. ПУБЛІКАЦІЯ НА ВСІ ПІДКЛЮЧЕНІ ПЛАТФОРМИ
            youtube_result = None
            youtube_error = None
            platform_results = {}
            if auto_upload is None:
                auto_upload = os.getenv('AUTO_UPLOAD', 'False').lower() == 'true'
            if publish_scope == 'create_only':
                auto_upload = False

            if auto_upload:
                target_platforms = (
                    ['youtube'] if publish_scope == 'youtube_only'
                    else enabled_platforms()
                )
                youtube_uploader = (
                    self.get_youtube_uploader(profile_id)
                    if 'youtube' in target_platforms else None
                )
                logger.info(
                    "Step 5/5: Publishing %s content via profile %s to %s...",
                    content_mode,
                    profile_id,
                    ','.join(target_platforms),
                )
                platform_metadata = build_platform_metadata(script, seo)
                platform_results = self.publisher.publish_all(
                    video_path=video_result['video_path'],
                    video_id=video_id,
                    metadata=platform_metadata,
                    youtube_uploader=youtube_uploader,
                    platforms=target_platforms,
                )
                if 'youtube' in platform_results:
                    platform_results['youtube']['profile_id'] = profile_id
                    platform_results['youtube']['profile_name'] = profile['name']
                youtube_status = platform_results.get('youtube') or {}
                if youtube_status.get('status') == 'published':
                    youtube_result = {
                        'video_id': youtube_status.get('platform_id'),
                        'url': youtube_status.get('url'),
                    }
                elif youtube_status.get('status') == 'failed':
                    youtube_error = youtube_status.get('error')

                for platform, result in platform_results.items():
                    logger.info(
                        "  %s: %s%s",
                        platform,
                        result.get('status'),
                        f" ({result.get('url')})" if result.get('url') else '',
                    )
            else:
                logger.info("Step 5/5: Skipping publishing (AUTO_UPLOAD=False)")

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
                'platform_results': platform_results,
                'created_at': datetime.utcnow().isoformat(),
                'ai_cost': script['metadata']['cost'] + (audio_result.get('cost', 0) or 0),
                'content_mode': content_mode,
                'profile_id': profile_id,
                'affiliate_offer_id': affiliate_offer_id,
            }

            self.db.add_video(video_data)

            # Оновлення статистики
            self.session_stats['videos_created'] += 1
            if youtube_result:
                self.session_stats['videos_uploaded'] += 1
            for platform, result in platform_results.items():
                if result.get('status') in ('published', 'processing', 'awaiting_user'):
                    uploads = self.session_stats['platform_uploads']
                    uploads[platform] = uploads.get(platform, 0) + 1
            self.session_stats['total_cost'] += video_data['ai_cost']

            logger.info(f"{'='*60}")
            logger.info(f"✓ VIDEO PRODUCTION COMPLETE: {video_id}")
            logger.info(f"{'='*60}")

            return {
                'video_id': video_id,
                'video_path': video_result['video_path'],
                'youtube_url': youtube_result['url'] if youtube_result else None,
                'youtube_video_id': youtube_result['video_id'] if youtube_result else None,
                'youtube_error': youtube_error,
                'platform_results': platform_results,
                'content_mode': content_mode,
                'profile_id': profile_id,
                'profile_name': profile['name'],
                'affiliate_offer_id': affiliate_offer_id,
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

    def get_youtube_uploader(self, profile_id: str = 'default') -> YouTubeUploader:
        """Create an isolated uploader so one profile can never use another token."""
        profile = self.db.get_channel_profile(profile_id, include_secrets=True)
        if not profile:
            raise ValueError('Профіль каналу не знайдено')
        return YouTubeUploader(
            refresh_token=profile.get('youtube_refresh_token'),
            use_token_file=False,
            privacy_status=profile.get('privacy_status') or 'public',
            allow_environment_token=False,
        )

    def produce_batch(
        self,
        count: int,
        niches: Optional[list] = None,
        trigger_source: str = 'manual',
    ) -> list:
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

                result = self.produce_video(
                    niche_id=niche,
                    trigger_source=trigger_source,
                )
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
        analytics = self.get_youtube_uploader(
            video.get('profile_id') or 'default'
        ).get_video_analytics(video['youtube_video_id'])

        # Розраховуємо ROI
        ai_cost = video.get('ai_cost', 0)
        views = analytics.get('views', 0)

        try:
            shorts_rpm = max(0.0, float(os.getenv('SHORTS_RPM_ESTIMATE', '0.075')))
        except ValueError:
            shorts_rpm = 0.075
        estimated_revenue = (views / 1000) * shorts_rpm
        affiliate_stats = self.db.get_affiliate_stats(video_id=video_id)
        affiliate_revenue = affiliate_stats.get('revenue', 0)
        total_revenue = estimated_revenue + affiliate_revenue

        return {
            'video_id': video_id,
            'youtube_video_id': video['youtube_video_id'],
            'title': video['title'],
            'niche': video['niche'],
            'created_at': video['created_at'],
            'analytics': analytics,
            'affiliate': affiliate_stats,
            'financials': {
                'ai_cost': ai_cost,
                'estimated_shorts_revenue': round(estimated_revenue, 4),
                'confirmed_affiliate_revenue': round(affiliate_revenue, 4),
                'estimated_revenue': round(total_revenue, 4),
                'roi': round((total_revenue / ai_cost - 1) * 100, 1) if ai_cost > 0 else 0,
                'profit': round(total_revenue - ai_cost, 4),
                'shorts_rpm_estimate': shorts_rpm,
            }
        }

    def get_top_performing_videos(self, limit: int = 10) -> list:
        """Топ відео по переглядам"""
        videos = self.db.list_videos(limit=100)

        # Отримуємо analytics для кожного
        with_analytics = []
        for video in videos:
            if video.get('youtube_video_id'):
                try:
                    analytics = self.get_youtube_uploader(
                        video.get('profile_id') or 'default'
                    ).get_video_analytics(video['youtube_video_id'])
                    video['analytics'] = analytics
                    with_analytics.append(video)
                except Exception as exc:
                    logger.warning(
                        "Could not read analytics for %s: %s",
                        video['video_id'], exc
                    )

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
