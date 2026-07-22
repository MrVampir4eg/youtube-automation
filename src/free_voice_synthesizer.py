"""Безкоштовна нейронна озвучка з надійним gTTS fallback."""

import asyncio
import os
import logging
from pathlib import Path
from typing import Dict
from gtts import gTTS
import time

try:
    import edge_tts
except ImportError:  # gTTS лишається резервним провайдером
    edge_tts = None

logger = logging.getLogger(__name__)


class FreeVoiceSynthesizer:
    """Нейронний Microsoft Edge TTS з автоматичним fallback на gTTS."""

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

        self.provider = os.getenv('FREE_TTS_PROVIDER', 'edge').lower()
        self.edge_rate = os.getenv('EDGE_TTS_RATE', '').strip()
        self.edge_pitch = os.getenv('EDGE_TTS_PITCH', '').strip()
        self.edge_voice = os.getenv('EDGE_TTS_VOICE', '').strip()

        selected = 'Edge Neural TTS' if self.provider == 'edge' else 'gTTS'
        logger.info(f"✓ FREE Voice Synthesizer initialized ({selected})")

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

        chars_count = len(text)

        logger.info(f"Synthesizing audio: {chars_count} chars, language: {language}")

        if self.provider == 'edge' and edge_tts is not None:
            try:
                return self._synthesize_edge(
                    text=text,
                    niche=niche,
                    video_id=video_id,
                    language=language
                )
            except Exception as exc:
                logger.warning(f"Edge TTS failed, falling back to gTTS: {exc}")

        return self._synthesize_gtts(
            text=text,
            video_id=video_id,
            language=language
        )

    def _select_edge_voice(self, niche: str, language: str) -> str:
        """Обрати природний голос; можна перевизначити через EDGE_TTS_VOICE."""
        if self.edge_voice:
            return self.edge_voice

        if language == 'uk':
            if niche in {
                'everyday_humor', 'internet_culture', 'tech', 'productivity'
            }:
                return 'uk-UA-OstapNeural'
            return 'uk-UA-PolinaNeural'
        if language == 'en':
            return 'en-US-EmmaMultilingualNeural'
        if language == 'ru':
            return 'ru-RU-SvetlanaNeural'
        return 'uk-UA-PolinaNeural'

    def _select_edge_settings(self, niche: str) -> tuple:
        """Natural niche-aware pace unless Render explicitly overrides it."""
        default_rates = {
            'everyday_humor': '+12%',
            'internet_culture': '+11%',
            'fun_facts': '+9%',
            'tech': '+8%',
            'productivity': '+7%',
            'mini_stories': '+5%',
            'history': '+3%',
            'psychology': '+2%'
        }
        rate = self.edge_rate or default_rates.get(niche, '+5%')
        pitch = self.edge_pitch or '+0Hz'
        return rate, pitch

    def _synthesize_edge(self,
                         text: str,
                         niche: str,
                         video_id: str,
                         language: str) -> Dict:
        """Створити MP3 і точні межі слів для динамічних субтитрів."""
        start_time = time.time()
        audio_path = self.output_dir / f"{video_id}.mp3"
        voice = self._select_edge_voice(niche, language)
        rate, pitch = self._select_edge_settings(niche)

        async def stream_audio():
            word_timings = []
            communicator = edge_tts.Communicate(
                text,
                voice,
                rate=rate,
                pitch=pitch,
                boundary='WordBoundary'
            )

            with audio_path.open('wb') as audio_file:
                async for chunk in communicator.stream():
                    if chunk['type'] == 'audio':
                        audio_file.write(chunk['data'])
                    elif chunk['type'] == 'WordBoundary':
                        word_timings.append({
                            'text': chunk.get('text', '').strip(),
                            'start': float(chunk.get('offset', 0)) / 10_000_000,
                            'duration': float(chunk.get('duration', 0)) / 10_000_000
                        })

            return [timing for timing in word_timings if timing['text']]

        try:
            word_timings = asyncio.run(stream_audio())
        except Exception:
            audio_path.unlink(missing_ok=True)
            raise

        if not audio_path.exists() or audio_path.stat().st_size == 0:
            raise RuntimeError('Edge TTS returned an empty audio file')

        duration = (
            word_timings[-1]['start'] + word_timings[-1]['duration']
            if word_timings else (len(text.split()) / 165) * 60
        )
        generation_time = time.time() - start_time

        logger.info(
            f"✓ Neural audio generated: {audio_path.name}, "
            f"~{duration:.1f}s, voice={voice}, rate={rate}, COST: $0"
        )

        return {
            'audio_path': audio_path,
            'duration': duration,
            'chars_used': len(text),
            'voice_used': voice,
            'word_timings': word_timings,
            'generation_time': generation_time,
            'cost': 0.0,
            'provider': 'edge-tts'
        }

    def _synthesize_gtts(self,
                         text: str,
                         video_id: str,
                         language: str) -> Dict:
        """Резервна озвучка, якщо Edge TTS тимчасово недоступний."""
        lang_code = self.languages.get(language, 'uk')
        chars_count = len(text)

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
                'word_timings': [],
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
            'provider': 'Edge Neural TTS + gTTS fallback',
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
            'provider': 'Edge Neural TTS / gTTS fallback',
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
