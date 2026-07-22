"""
Voice Synthesis Module
Генерація озвучки через ElevenLabs API
"""

import os
import logging
from typing import Dict, Optional
from pathlib import Path
from elevenlabs import ElevenLabs, VoiceSettings
import time

logger = logging.getLogger(__name__)


class VoiceSynthesizer:
    """Синтезатор мови для YouTube Shorts"""

    def __init__(self):
        self.client = ElevenLabs(api_key=os.getenv('ELEVENLABS_API_KEY'))

        # Маппінг голосів з конфігу
        self.voices = {
            'motivation': os.getenv('VOICE_MOTIVATION', 'Adam'),
            'finance': os.getenv('VOICE_FINANCE', 'Antoni'),
            'history': os.getenv('VOICE_HISTORY', 'Bella'),
            'tech': os.getenv('VOICE_TECH', 'Josh'),
            'productivity': os.getenv('VOICE_MOTIVATION', 'Adam')
        }

        # Налаштування якості
        self.voice_settings = VoiceSettings(
            stability=0.5,  # Баланс між стабільністю та виразністю
            similarity_boost=0.75,  # Схожість з оригінальним голосом
            style=0.0,  # Без специфічного стилю
            use_speaker_boost=True  # Покращення чіткості
        )

        # Трекінг використання
        self.chars_used_today = 0
        self.max_chars_per_day = int(os.getenv('MAX_ELEVENLABS_CHARS_PER_DAY', 1000))

        # Директорія для збереження
        self.output_dir = Path('output/audio')
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def synthesize(self,
                   text: str,
                   niche: str,
                   video_id: str,
                   custom_voice: Optional[str] = None) -> Dict:
        """
        Синтезація озвучки

        Args:
            text: Текст для озвучки
            niche: Ніша (для вибору голосу)
            video_id: Унікальний ID відео
            custom_voice: Кастомний голос (опційно)

        Returns:
            {
                'audio_path': Path,
                'duration': float,
                'chars_used': int,
                'voice_used': str
            }
        """

        # Перевірка ліміту
        chars_count = len(text)
        if self.chars_used_today + chars_count > self.max_chars_per_day:
            raise Exception(
                f"Daily character limit reached: "
                f"{self.chars_used_today}/{self.max_chars_per_day}"
            )

        # Вибір голосу
        voice_name = custom_voice or self.voices.get(niche, 'Adam')

        logger.info(f"Synthesizing audio: {chars_count} chars, voice: {voice_name}")

        try:
            start_time = time.time()

            # Генерація аудіо
            audio_generator = self.client.text_to_speech.convert(
                text=text,
                voice_id=self._get_voice_id(voice_name),
                model_id="eleven_multilingual_v2",  # Підтримка української
                voice_settings=self.voice_settings
            )

            # Збереження в файл
            audio_path = self.output_dir / f"{video_id}.mp3"

            # Записуємо audio stream у файл
            with open(audio_path, 'wb') as f:
                for chunk in audio_generator:
                    f.write(chunk)

            generation_time = time.time() - start_time

            # Оцінка тривалості (приблизно 150 слів на хвилину)
            words = len(text.split())
            estimated_duration = (words / 150) * 60  # секунди

            self.chars_used_today += chars_count

            logger.info(
                f"✓ Audio generated: {audio_path.name}, "
                f"~{estimated_duration:.1f}s, "
                f"{generation_time:.1f}s generation time"
            )

            return {
                'audio_path': audio_path,
                'duration': estimated_duration,
                'chars_used': chars_count,
                'voice_used': voice_name,
                'generation_time': generation_time
            }

        except Exception as e:
            logger.error(f"Voice synthesis error: {e}")
            raise

    def _get_voice_id(self, voice_name: str) -> str:
        """
        Отримання voice ID за назвою
        ElevenLabs має pre-made voices з конкретними IDs
        """
        voice_mapping = {
            # Pre-made voices (ці IDs публічні)
            'Adam': '21m00Tcm4TlvDq8ikWAM',
            'Antoni': 'ErXwobaYiN019PkySvjV',
            'Arnold': 'VR6AewLTigWG4xSOukaG',
            'Bella': 'EXAVITQu4vr4xnSDxMaL',
            'Domi': 'AZnzlk1XvdvUeBnXmlld',
            'Elli': 'MF3mGyEYCl7XYWbV9V6O',
            'Josh': 'TxGEqnHWrfWFTfGW9XjX',
            'Rachel': '21m00Tcm4TlvDq8ikWAM',
            'Sam': 'yoZ06aMxZJJ28mfd3POQ'
        }

        return voice_mapping.get(voice_name, voice_mapping['Adam'])

    def get_available_voices(self) -> Dict:
        """Список доступних голосів"""
        try:
            voices_response = self.client.voices.get_all()
            return {
                'voices': [
                    {
                        'voice_id': v.voice_id,
                        'name': v.name,
                        'category': v.category,
                        'description': getattr(v, 'description', '')
                    }
                    for v in voices_response.voices
                ]
            }
        except Exception as e:
            logger.error(f"Failed to fetch voices: {e}")
            return {'voices': []}

    def test_voice(self, voice_name: str, test_text: str = None) -> Path:
        """
        Тест голосу

        Args:
            voice_name: Назва голосу
            test_text: Текст для тесту (опційно)

        Returns:
            Path до тестового аудіо
        """
        if not test_text:
            test_text = "Привіт! Це тестова озвучка для YouTube Shorts. Як звучить цей голос?"

        result = self.synthesize(
            text=test_text,
            niche='test',
            video_id=f'test_{voice_name}_{int(time.time())}',
            custom_voice=voice_name
        )

        return result['audio_path']

    def get_usage_stats(self) -> Dict:
        """Статистика використання за сьогодні"""
        usage_percent = (self.chars_used_today / self.max_chars_per_day) * 100

        return {
            'chars_used': self.chars_used_today,
            'chars_limit': self.max_chars_per_day,
            'chars_remaining': self.max_chars_per_day - self.chars_used_today,
            'usage_percent': round(usage_percent, 1),
            'estimated_videos_remaining': (
                self.max_chars_per_day - self.chars_used_today
            ) // 300  # Приблизно 300 chars на відео
        }

    def estimate_cost(self, text: str) -> Dict:
        """
        Оцінка вартості озвучки

        ElevenLabs Starter plan: $5/міс = 30,000 chars
        = $0.000167 per char
        """
        chars = len(text)
        cost_per_char = 0.000167
        cost = chars * cost_per_char

        return {
            'chars': chars,
            'estimated_cost': round(cost, 4),
            'plan': 'Starter ($5/month)',
            'chars_per_dollar': 6000
        }

    def cleanup_old_audio(self, days: int = 7):
        """Видалення старих аудіо файлів"""
        import datetime

        cutoff = time.time() - (days * 86400)
        deleted = 0

        for audio_file in self.output_dir.glob('*.mp3'):
            if audio_file.stat().st_mtime < cutoff:
                audio_file.unlink()
                deleted += 1

        logger.info(f"Cleaned up {deleted} audio files older than {days} days")
        return deleted


class VoiceCache:
    """
    Кешування озвучки для повторюваного контенту
    (Наприклад, для CTA які повторюються)
    """

    def __init__(self, cache_dir: str = 'output/audio_cache'):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cache_key(self, text: str, voice: str) -> str:
        """Генерація ключа для кешу"""
        import hashlib
        content = f"{text}_{voice}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, text: str, voice: str) -> Optional[Path]:
        """Отримання з кешу"""
        key = self.get_cache_key(text, voice)
        cache_path = self.cache_dir / f"{key}.mp3"

        if cache_path.exists():
            logger.info(f"Cache hit: {key}")
            return cache_path

        return None

    def put(self, text: str, voice: str, audio_path: Path):
        """Збереження в кеш"""
        key = self.get_cache_key(text, voice)
        cache_path = self.cache_dir / f"{key}.mp3"

        # Копіюємо файл
        import shutil
        shutil.copy2(audio_path, cache_path)

        logger.info(f"Cached: {key}")


if __name__ == '__main__':
    # Тестування
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    synthesizer = VoiceSynthesizer()

    # Тест синтезу
    print("Тестування синтезу голосу...")

    test_script = """
    Привіт! Сьогодні я розповім тобі про 3 звички мільярдерів,
    які змінять твоє життя. Перша звичка - прокидатися о 5 ранку.
    Підпишись щоб дізнатись решту!
    """

    result = synthesizer.synthesize(
        text=test_script,
        niche='motivation',
        video_id='test_video_001'
    )

    print(f"\n✓ Аудіо створено: {result['audio_path']}")
    print(f"  Тривалість: ~{result['duration']:.1f}s")
    print(f"  Символів: {result['chars_used']}")
    print(f"  Голос: {result['voice_used']}")

    # Статистика
    stats = synthesizer.get_usage_stats()
    print(f"\n📊 Використання:")
    print(f"  {stats['chars_used']}/{stats['chars_limit']} символів ({stats['usage_percent']}%)")
    print(f"  Залишилось відео: ~{stats['estimated_videos_remaining']}")

    # Оцінка вартості
    cost = synthesizer.estimate_cost(test_script)
    print(f"\n💰 Вартість: ${cost['estimated_cost']}")
