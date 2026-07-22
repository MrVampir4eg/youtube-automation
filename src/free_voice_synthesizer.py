"""
FREE Voice Synthesizer - використовує Google Text-to-Speech (БЕЗКОШТОВНО!)
gTTS - якісна озвучка без API ключів
"""

import os
import logging
from pathlib import Path
from typing import Dict
from gtts import gTTS
import time

logger = logging.getLogger(__name__)


class FreeVoiceSynthesizer:
    """Безкоштовний синтезатор мови через gTTS"""

    def __init__(self):
        # Директорія для збереження
        self.output_dir = Path('output/audio')
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Підтримувані мови
        self.languages = {
            'uk': 'uk',  # Українська
            'en': 'en',  # Англійська
            'ru': 'ru',  # Російська
        }

        logger.info("✓ FREE Voice Synthesizer initialized (gTTS)")

    def synthesize(self,
                   text: str,
                   niche: str,
                   video_id: str,
                   language: str = 'uk') -> Dict:
        """
        Синтезація озвучки через Google TTS (БЕЗКОШТОВНО!)

        Args:
            text: Текст для озвучки
            niche: Ніша
            video_id: ID відео
            language: Мова ('uk', 'en', 'ru')

        Returns:
            {
                'audio_path': Path,
                'duration': float,
                'chars_used': int,
                'voice_used': str,
                'cost': 0.0  # БЕЗКОШТОВНО!
            }
        """

        lang_code = self.languages.get(language, 'uk')
        chars_count = len(text)

        logger.info(f"Synthesizing audio: {chars_count} chars, language: {lang_code}")

        try:
            start_time = time.time()

            # Генерація через gTTS
            tts = gTTS(
                text=text,
                lang=lang_code,
                slow=False,  # Нормальна швидкість
                lang_check=True
            )

            # Збереження
            audio_path = self.output_dir / f"{video_id}.mp3"
            tts.save(str(audio_path))

            generation_time = time.time() - start_time

            # Оцінка тривалості (приблизно)
            words = len(text.split())
            estimated_duration = (words / 150) * 60  # ~150 слів/хвилину

            logger.info(
                f"✓ Audio generated: {audio_path.name}, "
                f"~{estimated_duration:.1f}s, "
                f"{generation_time:.1f}s generation time, "
                f"COST: $0 (FREE!)"
            )

            return {
                'audio_path': audio_path,
                'duration': estimated_duration,
                'chars_used': chars_count,
                'voice_used': f'gTTS-{lang_code}',
                'generation_time': generation_time,
                'cost': 0.0,  # БЕЗКОШТОВНО!
                'provider': 'gTTS'
            }

        except Exception as e:
            logger.error(f"gTTS synthesis error: {e}")
            raise

    def test_voice(self, test_text: str = None, language: str = 'uk') -> Path:
        """
        Тест озвучки

        Args:
            test_text: Текст для тесту
            language: Мова

        Returns:
            Path до аудіо
        """
        if not test_text:
            test_text = "Привіт! Це тестова озвучка для YouTube Shorts через безкоштовний Google TTS."

        result = self.synthesize(
            text=test_text,
            niche='test',
            video_id=f'test_{int(time.time())}',
            language=language
        )

        return result['audio_path']

    def get_usage_stats(self) -> Dict:
        """Статистика використання"""
        return {
            'provider': 'gTTS',
            'cost': 0.0,
            'cost_per_video': 0.0,
            'monthly_cost': 0.0,
            'note': 'Повністю безкоштовно! 🎉'
        }

    def estimate_cost(self, text: str) -> Dict:
        """Оцінка вартості"""
        return {
            'chars': len(text),
            'estimated_cost': 0.0,
            'provider': 'gTTS (Google Text-to-Speech)',
            'note': 'БЕЗКОШТОВНО!'
        }

    def cleanup_old_audio(self, days: int = 7) -> int:
        """Видалення старих аудіо файлів"""
        cutoff = time.time() - (days * 86400)
        deleted = 0

        for audio_file in self.output_dir.glob('*.mp3'):
            if audio_file.stat().st_mtime < cutoff:
                audio_file.unlink()
                deleted += 1

        logger.info(f"Cleaned up {deleted} audio files older than {days} days")
        return deleted


# Альтернатива: pyttsx3 (офлайн, але менша якість)
class OfflineVoiceSynthesizer:
    """
    Повністю офлайн синтезатор через pyttsx3
    Не потребує інтернету, але якість нижча
    """

    def __init__(self):
        try:
            import pyttsx3
            self.engine = pyttsx3.init()

            # Налаштування голосу
            self.engine.setProperty('rate', 150)  # Швидкість
            self.engine.setProperty('volume', 1.0)  # Гучність

            self.output_dir = Path('output/audio')
            self.output_dir.mkdir(parents=True, exist_ok=True)

            logger.info("✓ Offline Voice Synthesizer initialized (pyttsx3)")

        except Exception as e:
            logger.error(f"Failed to initialize pyttsx3: {e}")
            raise

    def synthesize(self, text: str, niche: str, video_id: str) -> Dict:
        """Синтезація офлайн"""
        audio_path = self.output_dir / f"{video_id}.mp3"

        try:
            self.engine.save_to_file(text, str(audio_path))
            self.engine.runAndWait()

            # Оцінка тривалості
            words = len(text.split())
            estimated_duration = (words / 150) * 60

            return {
                'audio_path': audio_path,
                'duration': estimated_duration,
                'chars_used': len(text),
                'voice_used': 'pyttsx3-offline',
                'cost': 0.0,
                'provider': 'pyttsx3'
            }

        except Exception as e:
            logger.error(f"pyttsx3 error: {e}")
            raise


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    print("\n🆓 FREE Voice Synthesizer Test")
    print("="*60)

    synthesizer = FreeVoiceSynthesizer()

    # Тест українською
    test_script = """
    Привіт! Сьогодні я розповім тобі про 3 звички мільярдерів,
    які змінять твоє життя. Перша звичка - прокидатися о 5 ранку.
    Друга - читати мінімум годину щодня. Третя - медитувати.
    Підпишись щоб дізнатись більше!
    """

    result = synthesizer.synthesize(
        text=test_script.strip(),
        niche='motivation',
        video_id='test_free_voice_001',
        language='uk'
    )

    print(f"\n✓ Аудіо створено: {result['audio_path']}")
    print(f"  Тривалість: ~{result['duration']:.1f}s")
    print(f"  Символів: {result['chars_used']}")
    print(f"  Голос: {result['voice_used']}")
    print(f"  Провайдер: {result['provider']}")
    print(f"  💰 Вартість: ${result['cost']} (БЕЗКОШТОВНО!)")

    # Статистика
    stats = synthesizer.get_usage_stats()
    print(f"\n📊 Статистика:")
    print(f"  Провайдер: {stats['provider']}")
    print(f"  Вартість: ${stats['cost']}/міс")
    print(f"  Примітка: {stats['note']}")

    print("\n" + "="*60)
    print("✅ Тест завершено! Перевірте файл audio в output/audio/")
