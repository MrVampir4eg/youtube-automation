"""
Video Renderer
Створення YouTube Shorts з аудіо та візуалів
"""

import os
import logging
import random
from pathlib import Path
from typing import Dict, List, Optional
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# MoviePy 1.0.3 використовує стару назву Pillow, яку видалили у Pillow 10.
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

from moviepy.editor import (
    VideoFileClip, AudioFileClip, ImageClip,
    CompositeVideoClip, concatenate_videoclips
)
from moviepy.video.fx.fadein import fadein
from moviepy.video.fx.fadeout import fadeout
import time

logger = logging.getLogger(__name__)


class VideoRenderer:
    """Рендеринг YouTube Shorts відео"""

    def __init__(self):
        self.pexels_api_key = os.getenv('PEXELS_API_KEY')
        self.pixabay_api_key = os.getenv('PIXABAY_API_KEY')

        # Налаштування відео
        self.width = 1080
        self.height = 1920
        self.fps = int(os.getenv('VIDEO_FPS', 30))

        # Директорії
        self.output_dir = Path('output/videos')
        self.cache_dir = Path('output/video_cache')
        self.temp_dir = Path('output/temp')

        for d in [self.output_dir, self.cache_dir, self.temp_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def create_video(self,
                     audio_path: Path,
                     script_data: Dict,
                     video_id: str) -> Dict:
        """
        Створення повного відео

        Args:
            audio_path: Шлях до аудіо файлу
            script_data: Дані скрипту (з content_generator)
            video_id: Унікальний ID

        Returns:
            {
                'video_path': Path,
                'duration': float,
                'filesize': int,
                'resolution': str
            }
        """
        logger.info(f"Rendering video: {video_id}")
        start_time = time.time()

        try:
            # 1. Завантажити background відео/зображення
            background = self._get_background_media(
                script_data['video_themes'],
                script_data['estimated_duration']
            )

            # 2. Завантажити аудіо
            audio = AudioFileClip(str(audio_path))
            duration = audio.duration

            # 3. Підготувати background до потрібного розміру
            background_clip = self._prepare_background(background, duration)

            # 4. Додати субтитри
            if os.getenv('AUTO_CAPTIONS', 'True').lower() == 'true':
                video_with_subs = self._add_captions(
                    background_clip,
                    script_data,
                    duration
                )
            else:
                video_with_subs = background_clip

            # 5. Додати аудіо
            final_video = video_with_subs.set_audio(audio)

            # 6. Додати fade in/out
            final_video = fadein(final_video, 0.5)
            final_video = fadeout(final_video, 0.5)

            # 7. Експорт
            output_path = self.output_dir / f"{video_id}.mp4"

            final_video.write_videofile(
                str(output_path),
                fps=self.fps,
                codec='libx264',
                audio_codec='aac',
                preset='medium',
                threads=4,
                logger=None  # Вимкнути moviepy логи
            )

            # Cleanup
            background_clip.close()
            audio.close()
            if video_with_subs != background_clip:
                video_with_subs.close()
            final_video.close()

            render_time = time.time() - start_time
            filesize = output_path.stat().st_size

            logger.info(
                f"✓ Video rendered: {output_path.name}, "
                f"{duration:.1f}s, "
                f"{filesize/1024/1024:.1f}MB, "
                f"{render_time:.1f}s render time"
            )

            return {
                'video_path': output_path,
                'duration': duration,
                'filesize': filesize,
                'resolution': f"{self.width}x{self.height}",
                'render_time': render_time
            }

        except Exception as e:
            logger.error(f"Video rendering error: {e}")
            raise

    def _get_background_media(self, themes: List[str], duration: int) -> Path:
        """
        Завантаження background відео з Pexels

        Args:
            themes: Список тем (keywords)
            duration: Необхідна тривалість (секунди)

        Returns:
            Path до завантаженого файлу
        """
        # Вибираємо випадкову тему
        theme = random.choice(themes)

        # Перевіряємо кеш
        cache_key = f"{theme}_{duration}s"
        cache_path = self.cache_dir / f"{cache_key}.mp4"

        if cache_path.exists():
            logger.info(f"Using cached background: {cache_key}")
            return cache_path

        logger.info(f"Downloading background: theme={theme}, duration={duration}s")

        try:
            # Спроба завантажити з Pexels
            video_url = self._search_pexels_video(theme, duration)

            if video_url:
                # Завантажуємо відео
                response = requests.get(video_url, stream=True, timeout=60)
                response.raise_for_status()

                with open(cache_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                logger.info(f"✓ Downloaded: {cache_path.name}")
                return cache_path

            # Fallback: статичне зображення з Pexels
            logger.warning("No video found, using static image")
            return self._get_static_background(theme)

        except Exception as e:
            logger.error(f"Failed to get background: {e}")
            # Fallback: створюємо градієнт
            return self._create_gradient_background()

    def _search_pexels_video(self, query: str, min_duration: int) -> Optional[str]:
        """Пошук відео на Pexels"""
        if not self.pexels_api_key:
            logger.warning("No Pexels API key configured")
            return None

        url = "https://api.pexels.com/videos/search"
        headers = {"Authorization": self.pexels_api_key}
        params = {
            "query": query,
            "per_page": 15,
            "orientation": "portrait"
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 401:
                logger.warning("Pexels API key was rejected; using generated background")
                self.pexels_api_key = None
                return None
            response.raise_for_status()
            data = response.json()

            # Фільтруємо відео по тривалості
            for video in data.get('videos', []):
                if video['duration'] >= min_duration:
                    # Шукаємо HD portrait версію
                    for file in video['video_files']:
                        if (file.get('width') == 1080 and
                            file.get('height') >= 1920):
                            return file['link']

                    # Якщо немає exact match, беремо найкращу якість
                    best = max(video['video_files'],
                              key=lambda x: x.get('width', 0) * x.get('height', 0))
                    return best['link']

            return None

        except Exception as e:
            logger.error(f"Pexels API error: {e}")
            return None

    def _get_static_background(self, query: str) -> Path:
        """Завантаження статичного зображення"""
        cache_path = self.cache_dir / f"img_{query}.jpg"

        if cache_path.exists():
            return cache_path

        if not self.pexels_api_key:
            return self._create_gradient_background()

        url = "https://api.pexels.com/v1/search"
        headers = {"Authorization": self.pexels_api_key}
        params = {
            "query": query,
            "per_page": 15,
            "orientation": "portrait"
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 401:
                logger.warning("Pexels API key was rejected; using generated background")
                self.pexels_api_key = None
                return self._create_gradient_background()
            response.raise_for_status()
            data = response.json()

            if data.get('photos'):
                photo = random.choice(data['photos'])
                img_url = photo['src']['large2x']

                # Завантажуємо
                img_response = requests.get(img_url, timeout=30)
                img_response.raise_for_status()

                with open(cache_path, 'wb') as f:
                    f.write(img_response.content)

                return cache_path

        except Exception as e:
            logger.error(f"Failed to get image: {e}")

        # Fallback
        return self._create_gradient_background()

    def _create_gradient_background(self) -> Path:
        """Створення градієнтного background як fallback"""
        cache_path = self.cache_dir / "gradient_default.jpg"

        if cache_path.exists():
            return cache_path

        # Створюємо красивий градієнт
        img = Image.new('RGB', (self.width, self.height))
        draw = ImageDraw.Draw(img)

        # Темно-синій до фіолетового градієнт
        for y in range(self.height):
            r = int(30 + (120 * y / self.height))
            g = int(30 + (50 * y / self.height))
            b = int(80 + (150 * y / self.height))
            draw.line([(0, y), (self.width, y)], fill=(r, g, b))

        # Додаємо blur для smooth look
        img = img.filter(ImageFilter.GaussianBlur(radius=20))

        img.save(cache_path, quality=95)
        return cache_path

    def _prepare_background(self, media_path: Path, duration: float) -> VideoFileClip:
        """Підготовка background до потрібних розмірів"""

        if media_path.suffix in ['.mp4', '.mov', '.avi']:
            # Відео
            clip = VideoFileClip(str(media_path))

            # Якщо відео коротше ніж потрібно, loop
            if clip.duration < duration:
                n_loops = int(duration / clip.duration) + 1
                clip = concatenate_videoclips([clip] * n_loops)

            # Обрізаємо до потрібної тривалості
            clip = clip.subclip(0, min(clip.duration, duration))

        else:
            # Зображення - робимо статичний clip
            clip = ImageClip(str(media_path), duration=duration)

        # Resize до 1080x1920 (portrait)
        clip = clip.resize((self.width, self.height))

        return clip

    def _add_captions(self,
                     video_clip: VideoFileClip,
                     script_data: Dict,
                     duration: float) -> CompositeVideoClip:
        """
        Додавання субтитрів до відео

        Розбиваємо текст на частини та показуємо як TikTok-стиль
        """

        full_text = script_data['full_script']

        # Розбиваємо на речення
        sentences = full_text.replace('\n\n', '. ').split('. ')
        sentences = [s.strip() + '.' for s in sentences if s.strip()]

        # Розраховуємо час для кожного речення
        time_per_sentence = duration / len(sentences)

        text_clips = []

        for i, sentence in enumerate(sentences):
            start_time = i * time_per_sentence

            # Розбиваємо довгі речення на кілька рядків
            words = sentence.split()
            lines = []
            current_line = []

            for word in words:
                current_line.append(word)
                if len(' '.join(current_line)) > 30:  # Max 30 chars per line
                    lines.append(' '.join(current_line))
                    current_line = []

            if current_line:
                lines.append(' '.join(current_line))

            text = '\n'.join(lines)

            # Pillow-капшен не потребує ImageMagick у Docker/Render.
            txt_clip = self._create_caption_clip(text)

            txt_clip = txt_clip.set_position('center')
            txt_clip = txt_clip.set_start(start_time)
            txt_clip = txt_clip.set_duration(time_per_sentence)

            # Додаємо fade in/out
            txt_clip = fadein(txt_clip, 0.2)
            txt_clip = fadeout(txt_clip, 0.2)

            text_clips.append(txt_clip)

        # Композит відео + текст
        final = CompositeVideoClip([video_clip] + text_clips)

        return final

    def _create_caption_clip(self, text: str) -> ImageClip:
        """Створити прозорий caption clip через Pillow."""
        font_paths = [
            os.getenv('CAPTION_FONT'),
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf'
        ]

        font = None
        for font_path in font_paths:
            if font_path and Path(font_path).exists():
                font = ImageFont.truetype(font_path, 60)
                break
        if font is None:
            font = ImageFont.load_default()

        lines = text.split('\n')
        image = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        line_spacing = 14
        line_boxes = [
            draw.textbbox((0, 0), line, font=font, stroke_width=3)
            for line in lines
        ]
        line_heights = [box[3] - box[1] for box in line_boxes]
        total_height = sum(line_heights) + line_spacing * max(0, len(lines) - 1)
        y = (self.height - total_height) // 2

        for line, box, line_height in zip(lines, line_boxes, line_heights):
            line_width = box[2] - box[0]
            x = (self.width - line_width) // 2
            draw.text(
                (x, y),
                line,
                font=font,
                fill='white',
                stroke_width=3,
                stroke_fill='black'
            )
            y += line_height + line_spacing

        return ImageClip(np.array(image), transparent=True)

    def add_watermark(self, video_path: Path, channel_name: str) -> Path:
        """Додавання watermark (опційно)"""
        # TODO: Implement watermark if needed
        pass

    def get_video_info(self, video_path: Path) -> Dict:
        """Отримання інформації про відео"""
        clip = VideoFileClip(str(video_path))

        info = {
            'duration': clip.duration,
            'fps': clip.fps,
            'size': (clip.w, clip.h),
            'filesize': video_path.stat().st_size,
            'has_audio': clip.audio is not None
        }

        clip.close()
        return info


if __name__ == '__main__':
    # Тестування
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    renderer = VideoRenderer()

    # Тестові дані
    test_script = {
        'hook': 'Ця людина заробила мільйон за рік!',
        'body': 'Він почав з нуля. Кожен день вставав о 5 ранку. '
                'Працював над своїм проєктом. Не здавався навіть коли було важко.',
        'cta': 'Підпишись щоб дізнатись більше історій успіху!',
        'full_script': 'Ця людина заробила мільйон за рік!\n\n'
                      'Він почав з нуля. Кожен день вставав о 5 ранку. '
                      'Працював над своїм проєктом. Не здавався навіть коли було важко.\n\n'
                      'Підпишись щоб дізнатись більше історій успіху!',
        'estimated_duration': 15,
        'video_themes': ['success', 'motivation', 'achievement'],
        'niche': 'motivation'
    }

    # Створюємо тестове аудіо (для тесту використаємо заглушку)
    test_audio = Path('output/audio/test_video_001.mp3')

    if test_audio.exists():
        print("Рендеринг тестового відео...")

        result = renderer.create_video(
            audio_path=test_audio,
            script_data=test_script,
            video_id='test_render_001'
        )

        print(f"\n✓ Відео створено: {result['video_path']}")
        print(f"  Тривалість: {result['duration']:.1f}s")
        print(f"  Розмір: {result['filesize']/1024/1024:.1f}MB")
        print(f"  Час рендерингу: {result['render_time']:.1f}s")
    else:
        print("⚠ Спочатку створіть тестове аудіо через voice_synthesizer.py")
