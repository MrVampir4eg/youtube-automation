"""
Video Renderer
Створення YouTube Shorts з аудіо та візуалів
"""

import os
import hashlib
import math
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
from moviepy.video.fx.crop import crop
import time

logger = logging.getLogger(__name__)


class VideoRenderer:
    """Рендеринг YouTube Shorts відео"""

    def __init__(self):
        self.pexels_api_key = os.getenv('PEXELS_API_KEY')
        self.pixabay_api_key = os.getenv('PIXABAY_API_KEY')
        self._pexels_warning_emitted = False
        self.scene_duration = max(
            1.8,
            float(os.getenv('SCENE_DURATION_SECONDS', 2.8))
        )

        # Free Render instance має мало RAM, тому за замовчуванням
        # рендеримо 540x960. Якість можна підняти через env.
        free_mode = os.getenv('USE_FREE_MODE', 'False').lower() == 'true'
        low_memory_mode = os.getenv(
            'LOW_MEMORY_MODE',
            'True' if free_mode else 'False'
        ).lower() == 'true'
        requested_width = int(os.getenv('VIDEO_WIDTH', 540 if free_mode else 1080))
        requested_height = int(os.getenv('VIDEO_HEIGHT', 960 if free_mode else 1920))
        requested_fps = int(os.getenv('VIDEO_FPS', 24 if free_mode else 30))
        requested_threads = int(os.getenv('VIDEO_THREADS', 1 if free_mode else 2))

        self.width = min(requested_width, 540) if low_memory_mode else requested_width
        self.height = min(requested_height, 960) if low_memory_mode else requested_height
        self.fps = min(requested_fps, 24) if low_memory_mode else requested_fps
        self.render_threads = min(requested_threads, 1) if low_memory_mode else requested_threads
        self.render_preset = os.getenv(
            'VIDEO_PRESET',
            'ultrafast' if low_memory_mode else 'medium'
        )

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
        background_parts = []

        try:
            # 1. Реальна тривалість визначається готовою озвучкою.
            audio = AudioFileClip(str(audio_path))
            duration = audio.duration

            # 2. Кілька коротких сцен замість одного статичного фону.
            queries = (
                script_data.get('visual_queries')
                or script_data.get('video_themes')
                or ['interesting discovery']
            )
            queries = list(dict.fromkeys(query for query in queries if query))
            random.shuffle(queries)

            # 6-14 hard cuts keep a short visually alive without turning it
            # into an unreadable slideshow.
            scene_count = max(6, min(14, math.ceil(duration / self.scene_duration)))
            segment_duration = duration / scene_count

            for index in range(scene_count):
                query = queries[index % len(queries)]
                media_path = self._get_background_media(
                    [query],
                    max(3, math.ceil(segment_duration))
                )
                background_parts.append(
                    self._prepare_background(media_path, segment_duration)
                )

            background_clip = (
                concatenate_videoclips(background_parts, method='compose')
                if len(background_parts) > 1 else background_parts[0]
            ).subclip(0, duration)

            # 3. Додати короткі синхронні субтитри
            if os.getenv('AUTO_CAPTIONS', 'True').lower() == 'true':
                video_with_subs = self._add_captions(
                    background_clip,
                    script_data,
                    duration
                )
            else:
                video_with_subs = background_clip

            # 4. Додати аудіо
            final_video = video_with_subs.set_audio(audio)

            # 5. Короткий fade не витрачає дорогоцінну першу секунду.
            final_video = fadein(final_video, 0.12)
            final_video = fadeout(final_video, 0.2)

            # 6. Експорт
            output_path = self.output_dir / f"{video_id}.mp4"

            final_video.write_videofile(
                str(output_path),
                fps=self.fps,
                codec='libx264',
                audio_codec='aac',
                preset=self.render_preset,
                threads=self.render_threads,
                logger=None  # Вимкнути moviepy логи
            )

            # Cleanup
            background_clip.close()
            for part in background_parts:
                if part is not background_clip:
                    part.close()
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
        cache_key = hashlib.sha1(
            f"{theme}|{duration}|{self.width}x{self.height}".encode('utf-8')
        ).hexdigest()[:16]
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
            logger.info("Stock video unavailable for this scene; using visual fallback")
            return self._get_static_background(theme)

        except Exception as e:
            logger.error(f"Failed to get background: {e}")
            # Fallback: створюємо градієнт
            return self._create_gradient_background(theme)

    def _search_pexels_video(self, query: str, min_duration: int) -> Optional[str]:
        """Пошук відео на Pexels"""
        if not self.pexels_api_key:
            if not self._pexels_warning_emitted:
                logger.warning(
                    "No Pexels API key configured; using generated multi-scene backgrounds"
                )
                self._pexels_warning_emitted = True
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

            candidates = [
                video for video in data.get('videos', [])
                if video.get('duration', 0) >= min_duration
            ]
            if candidates:
                video = random.choice(candidates[:10])
                files = video.get('video_files', [])
                portrait_files = [
                    file for file in files
                    if file.get('height', 0) > file.get('width', 0)
                ]
                usable_files = portrait_files or files
                if usable_files:
                    # Достатня якість без зайвого навантаження на Render Free.
                    best = min(
                        usable_files,
                        key=lambda file: abs(
                            (file.get('width', self.width) or self.width)
                            - self.width
                        )
                    )
                    return best['link']

            return None

        except Exception as e:
            logger.error(f"Pexels API error: {e}")
            return None

    def _get_static_background(self, query: str) -> Path:
        """Завантаження статичного зображення"""
        query_key = hashlib.sha1(query.encode('utf-8')).hexdigest()[:14]
        cache_path = self.cache_dir / f"img_{query_key}.jpg"

        if cache_path.exists():
            return cache_path

        if not self.pexels_api_key:
            return self._create_gradient_background(query)

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
        return self._create_gradient_background(query)

    def _create_gradient_background(self, theme: str = 'generic') -> Path:
        """Створення різних атмосферних фонів, якщо stock API недоступний."""
        theme_key = hashlib.sha1(theme.encode('utf-8')).hexdigest()[:12]
        cache_path = self.cache_dir / f"gradient_{theme_key}.jpg"

        if cache_path.exists():
            return cache_path

        digest = hashlib.sha256(theme.encode('utf-8')).digest()
        start = (
            18 + digest[0] % 48,
            15 + digest[1] % 42,
            45 + digest[2] % 90
        )
        end = (
            70 + digest[3] % 130,
            35 + digest[4] % 110,
            90 + digest[5] % 150
        )

        img = Image.new('RGB', (self.width, self.height))
        draw = ImageDraw.Draw(img)

        for y in range(self.height):
            ratio = y / max(1, self.height - 1)
            r = int(start[0] + (end[0] - start[0]) * ratio)
            g = int(start[1] + (end[1] - start[1]) * ratio)
            b = int(start[2] + (end[2] - start[2]) * ratio)
            draw.line([(0, y), (self.width, y)], fill=(r, g, b))

        # Абстрактні світлові плями дають рух при частій зміні сцен.
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        for index in range(3):
            radius = self.width // (3 + index)
            x = digest[6 + index] / 255 * self.width
            y = digest[9 + index] / 255 * self.height
            overlay_draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=(255, 255, 255, 22 + index * 8)
            )
        overlay = overlay.filter(ImageFilter.GaussianBlur(radius=self.width // 10))
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')

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

            # Один кешований ролик виглядає по-різному завдяки випадковій
            # стартовій точці, але завжди має точну тривалість сцени.
            max_start = max(0.0, clip.duration - duration)
            start = random.uniform(0.0, max_start) if max_start > 0.35 else 0.0
            clip = clip.subclip(start, min(clip.duration, start + duration))

        else:
            # Зображення - робимо статичний clip
            clip = ImageClip(str(media_path), duration=duration)

        # Aspect-fill без розтягування облич та предметів.
        scale = max(self.width / clip.w, self.height / clip.h)
        clip = clip.resize(scale)
        clip = crop(
            clip,
            x_center=clip.w / 2,
            y_center=clip.h / 2,
            width=self.width,
            height=self.height
        )

        return clip

    def _add_captions(self,
                     video_clip: VideoFileClip,
                     script_data: Dict,
                     duration: float) -> CompositeVideoClip:
        """Додати короткі caption-блоки, синхронізовані з Edge TTS."""
        segments = self._build_caption_segments(script_data, duration)
        text_clips = []
        caption_y = int(
            self.height * float(os.getenv('CAPTION_Y_RATIO', 0.62))
        )

        for segment in segments:
            style = 'hook' if segment['start'] < 1.6 else 'normal'
            txt_clip = self._create_caption_clip(
                segment['text'],
                highlight_last=True,
                style=style
            )
            txt_clip = txt_clip.set_position(('center', caption_y))
            txt_clip = txt_clip.set_start(segment['start'])
            txt_clip = txt_clip.set_duration(segment['duration'])
            txt_clip = fadein(txt_clip, 0.06)
            txt_clip = fadeout(txt_clip, 0.06)

            text_clips.append(txt_clip)

        # Невеликі attention-reset плашки підтримують ритм між змінами сцен.
        callouts = [
            value for value in script_data.get('on_screen_text', [])
            if value
        ][:4]
        for index, value in enumerate(callouts):
            start = duration * (index + 1) / (len(callouts) + 2)
            callout = self._create_caption_clip(
                value.upper(),
                style='callout'
            )
            callout = callout.set_position(('center', int(self.height * 0.16)))
            callout = callout.set_start(start)
            callout = callout.set_duration(min(1.0, max(0.55, duration - start)))
            callout = fadein(callout, 0.08)
            callout = fadeout(callout, 0.1)
            text_clips.append(callout)

        # CTA лишається візуальним, щоб озвучений фінал міг природно
        # зациклитися назад у першу фразу.
        cta_text = script_data.get('cta', '').strip()
        if cta_text and duration > 2:
            cta_duration = min(1.8, duration * 0.12)
            cta = self._create_caption_clip(cta_text.upper(), style='cta')
            cta = cta.set_position(('center', int(self.height * 0.12)))
            cta = cta.set_start(max(0.0, duration - cta_duration))
            cta = cta.set_duration(cta_duration)
            cta = fadein(cta, 0.1)
            text_clips.append(cta)

        # Композит відео + текст
        final = CompositeVideoClip([video_clip] + text_clips)

        return final

    def _build_caption_segments(self, script_data: Dict, duration: float) -> List[Dict]:
        """Побудувати 2-4-слівні caption-блоки з точними або оціненими таймінгами."""
        words_per_caption = max(
            2,
            min(4, int(os.getenv('CAPTION_WORDS', 3)))
        )
        timings = [
            timing for timing in script_data.get('word_timings', [])
            if timing.get('text')
        ]

        if timings:
            groups = [
                timings[index:index + words_per_caption]
                for index in range(0, len(timings), words_per_caption)
            ]
            segments = []
            for index, group in enumerate(groups):
                start = max(0.0, float(group[0].get('start', 0)))
                if index + 1 < len(groups):
                    end = float(groups[index + 1][0].get('start', start + 0.5))
                else:
                    last = group[-1]
                    end = float(last.get('start', start)) + float(
                        last.get('duration', 0.4)
                    ) + 0.15

                end = min(duration, max(start + 0.32, end))
                if start >= duration:
                    continue
                segments.append({
                    'text': ' '.join(item['text'] for item in group),
                    'start': start,
                    'duration': end - start
                })
            return segments

        words = script_data.get('full_script', '').split()
        if not words:
            return []

        seconds_per_word = duration / len(words)
        segments = []
        for index in range(0, len(words), words_per_caption):
            group = words[index:index + words_per_caption]
            start = index * seconds_per_word
            end = min(duration, (index + len(group)) * seconds_per_word)
            segments.append({
                'text': ' '.join(group),
                'start': start,
                'duration': max(0.32, end - start)
            })
        return segments

    def _create_caption_clip(self,
                             text: str,
                             highlight_last: bool = False,
                             style: str = 'normal') -> ImageClip:
        """Створити читабельний caption із темною плашкою та жовтим акцентом."""
        font_paths = [
            os.getenv('CAPTION_FONT'),
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf'
        ]

        size_multiplier = {
            'hook': 1.16,
            'callout': 0.82,
            'cta': 0.86
        }.get(style, 1.0)
        font_size = max(30, round(self.width * 76 / 1080 * size_multiplier))
        stroke_width = max(2, round(self.width * 4 / 1080))
        font = None
        for font_path in font_paths:
            if font_path and Path(font_path).exists():
                font = ImageFont.truetype(font_path, font_size)
                break
        if font is None:
            font = ImageFont.load_default()

        probe = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
        draw = ImageDraw.Draw(probe)

        tokens = text.split()
        lines = []
        current_line = []
        for token in tokens:
            candidate = ' '.join(current_line + [token])
            candidate_width = draw.textbbox((0, 0), candidate, font=font)[2]
            if current_line and candidate_width > self.width * 0.82:
                lines.append(current_line)
                current_line = [token]
            else:
                current_line.append(token)
        if current_line:
            lines.append(current_line)

        line_height = draw.textbbox((0, 0), 'Аgj', font=font)[3]
        line_spacing = max(8, font_size // 4)
        total_height = len(lines) * line_height + max(0, len(lines) - 1) * line_spacing
        padding_x = max(18, font_size // 2)
        padding_y = max(12, font_size // 3)
        image = Image.new(
            'RGBA',
            (self.width, total_height + padding_y * 2),
            (0, 0, 0, 0)
        )
        draw = ImageDraw.Draw(image)
        line_widths = [
            draw.textbbox((0, 0), ' '.join(line), font=font)[2]
            for line in lines
        ]
        box_width = min(self.width - 12, max(line_widths, default=0) + padding_x * 2)
        box_left = (self.width - box_width) // 2
        box_fill = (
            (255, 213, 74, 232)
            if style in {'callout', 'cta'}
            else (0, 0, 0, 195 if style == 'hook' else 165)
        )
        draw.rounded_rectangle(
            (box_left, 0, box_left + box_width, image.height),
            radius=max(12, font_size // 2),
            fill=box_fill
        )

        y = padding_y
        token_index = 0
        last_token_index = max(0, len(tokens) - 1)
        space_width = draw.textbbox((0, 0), ' ', font=font)[2]

        for line, line_width in zip(lines, line_widths):
            x = (self.width - line_width) // 2
            for token in line:
                if style in {'callout', 'cta'}:
                    fill = '#111111'
                    token_stroke_width = 0
                    token_stroke_fill = '#111111'
                else:
                    fill = (
                        '#FFD54A'
                        if highlight_last and token_index == last_token_index
                        else 'white'
                    )
                    token_stroke_width = stroke_width
                    token_stroke_fill = 'black'
                draw.text(
                    (x, y),
                    token,
                    font=font,
                    fill=fill,
                    stroke_width=token_stroke_width,
                    stroke_fill=token_stroke_fill
                )
                token_width = draw.textbbox((0, 0), token, font=font)[2]
                x += token_width + space_width
                token_index += 1
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
