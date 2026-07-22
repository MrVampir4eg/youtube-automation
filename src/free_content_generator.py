"""
FREE Content Generator - використовує БЕЗКОШТОВНІ AI API
Groq API (llama-3.1-70b) - швидкий і якісний, повністю безкоштовно!
"""

import os
import json
import random
import logging
from typing import Dict, List, Optional
from datetime import datetime
import requests

logger = logging.getLogger(__name__)


class FreeContentGenerator:
    """Генератор контенту через БЕЗКОШТОВНІ API"""

    def __init__(self):
        # Groq API - БЕЗКОШТОВНО! https://groq.com/
        self.groq_api_key = os.getenv('GROQ_API_KEY', '')
        self.groq_model = 'llama-3.3-70b-versatile'

        # Together AI - БЕЗКОШТОВНО! https://together.ai/
        self.together_api_key = os.getenv('TOGETHER_API_KEY', '')

        # Вибираємо провайдера
        if self.groq_api_key:
            self.provider = 'groq'
            logger.info("✓ Using Groq API (FREE)")
        elif self.together_api_key:
            self.provider = 'together'
            logger.info("✓ Using Together AI (FREE)")
        else:
            logger.warning("⚠ No API keys found - using fallback templates")
            self.provider = 'fallback'

        # Завантаження конфігурації ніш
        config_path = 'config/niches.json'
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        else:
            logger.warning(f"Config not found: {config_path}, using defaults")
            self.config = self._get_default_config()

        self.niches = {n['id']: n for n in self.config['niches']}
        self.global_settings = self.config['global_settings']

    def _get_default_config(self):
        """Дефолтна конфігурація якщо файл не знайдено"""
        return {
            'niches': [
                {
                    'id': 'motivation',
                    'name': 'Мотивація',
                    'keywords': ['motivation', 'success', 'mindset']
                }
            ],
            'global_settings': {
                'min_duration_seconds': 45,
                'max_duration_seconds': 55,
                'words_per_second': 2.5
            }
        }

    def generate_script(self, niche_id: Optional[str] = None) -> Dict:
        """Генерація скрипту"""
        logger.info(f"Generating script for niche: {niche_id or 'random'}")

        # Вибір ніші
        if niche_id and niche_id in self.niches:
            niche = self.niches[niche_id]
        else:
            niche = random.choice(list(self.niches.values()))

        # Генерація через обраний провайдер
        if self.provider == 'groq':
            script_data = self._generate_groq(niche)
        elif self.provider == 'together':
            script_data = self._generate_together(niche)
        else:
            script_data = self._generate_fallback(niche)

        return script_data

    def _generate_groq(self, niche: Dict) -> Dict:
        """Генерація через Groq API (БЕЗКОШТОВНО!)"""

        prompt = self._build_prompt(niche)

        try:
            response = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {self.groq_api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': self.groq_model,
                    'messages': [
                        {
                            'role': 'system',
                            'content': 'Ти експерт-копірайтер для вірусного YouTube Shorts контенту.'
                        },
                        {
                            'role': 'user',
                            'content': prompt
                        }
                    ],
                    'temperature': 0.9,
                    'max_tokens': 500
                },
                timeout=30
            )

            response.raise_for_status()
            data = response.json()

            content = data['choices'][0]['message']['content']

            # Парсинг відповіді
            parsed = self._parse_script(content)

            return {
                'niche': niche['id'],
                'niche_name': niche['name'],
                'hook': parsed['hook'],
                'body': parsed['body'],
                'cta': parsed['cta'],
                'full_script': parsed['full_script'],
                'estimated_duration': self._estimate_duration(parsed['full_script']),
                'voice': niche.get('voice', 'uk'),
                'keywords': niche.get('keywords', []),
                'video_themes': niche.get('video_themes', ['generic']),
                'metadata': {
                    'generated_at': datetime.utcnow().isoformat(),
                    'provider': 'groq',
                    'model': self.groq_model,
                    'cost': 0.0  # БЕЗКОШТОВНО!
                }
            }

        except Exception as e:
            logger.error(f"Groq API error: {e}")
            # Fallback
            return self._generate_fallback(niche)

    def _generate_together(self, niche: Dict) -> Dict:
        """Генерація через Together AI (БЕЗКОШТОВНО!)"""

        prompt = self._build_prompt(niche)

        try:
            response = requests.post(
                'https://api.together.xyz/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {self.together_api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo',
                    'messages': [
                        {
                            'role': 'system',
                            'content': 'Ти експерт-копірайтер для вірусного YouTube Shorts контенту.'
                        },
                        {
                            'role': 'user',
                            'content': prompt
                        }
                    ],
                    'temperature': 0.9,
                    'max_tokens': 500
                },
                timeout=30
            )

            response.raise_for_status()
            data = response.json()

            content = data['choices'][0]['message']['content']
            parsed = self._parse_script(content)

            return {
                'niche': niche['id'],
                'niche_name': niche['name'],
                'hook': parsed['hook'],
                'body': parsed['body'],
                'cta': parsed['cta'],
                'full_script': parsed['full_script'],
                'estimated_duration': self._estimate_duration(parsed['full_script']),
                'voice': niche.get('voice', 'uk'),
                'keywords': niche.get('keywords', []),
                'video_themes': niche.get('video_themes', ['generic']),
                'metadata': {
                    'generated_at': datetime.utcnow().isoformat(),
                    'provider': 'together',
                    'model': 'llama-3.1-70b',
                    'cost': 0.0
                }
            }

        except Exception as e:
            logger.error(f"Together AI error: {e}")
            return self._generate_fallback(niche)

    def _generate_fallback(self, niche: Dict) -> Dict:
        """Fallback генерація без AI - використовує темплейти"""

        templates = {
            'motivation': [
                {
                    'hook': 'Ця людина змінила своє життя за 90 днів. Як?',
                    'body': 'Він встав о 5 ранку кожен день. Тренувався годину. Читав 30 хвилин. І найголовніше - не здавався навіть коли було важко. Результат? Повна трансформація тіла і розуму.',
                    'cta': 'Підпишись щоб дізнатись більше історій успіху!'
                },
                {
                    'hook': '3 звички мільярдерів про які ніхто не говорить',
                    'body': 'Перша - вони читають мінімум годину щодня. Друга - медитують кожен ранок. Третя - завжди інвестують в себе. Це не секрет, це дисципліна.',
                    'cta': 'Збережи щоб не забути ці звички!'
                }
            ],
            'finance': [
                {
                    'hook': '99% людей НЕ знають цей факт про гроші',
                    'body': 'Гроші - це не мета, це інструмент. Багаті люди заробляють гроші не заради грошей, а заради свободи. Свободи вибору. Свободи часу. Свободи життя.',
                    'cta': 'Підпишись для фінансових інсайтів!'
                }
            ]
        }

        niche_id = niche['id']
        available = templates.get(niche_id, templates['motivation'])
        template = random.choice(available)

        full_script = f"{template['hook']}\n\n{template['body']}\n\n{template['cta']}"

        return {
            'niche': niche_id,
            'niche_name': niche['name'],
            'hook': template['hook'],
            'body': template['body'],
            'cta': template['cta'],
            'full_script': full_script,
            'estimated_duration': self._estimate_duration(full_script),
            'voice': niche.get('voice', 'uk'),
            'keywords': niche.get('keywords', []),
            'video_themes': niche.get('video_themes', ['generic']),
            'metadata': {
                'generated_at': datetime.utcnow().isoformat(),
                'provider': 'fallback',
                'model': 'template',
                'cost': 0.0
            }
        }

    def _build_prompt(self, niche: Dict) -> str:
        """Побудова промпту"""
        return f"""Створи захоплюючий скрипт для YouTube Shorts на тему "{niche['name']}".

ВИМОГИ:
- Тривалість: 45-55 секунд (110-140 слів)
- Мова: Українська
- Стиль: Динамічний, захоплюючий

СТРУКТУРА:

HOOK (перші 3-5 секунд):
Має МОМЕНТАЛЬНО захопити увагу

BODY (основна частина):
Цікаві факти, історія, корисна інформація

CTA (останні 3-5 секунд):
Заклик до підписки

ФОРМАТ ВІДПОВІДІ:

HOOK:
[текст]

BODY:
[текст]

CTA:
[текст]

Створи скрипт ЗАРАЗ:"""

    def _parse_script(self, content: str) -> Dict:
        """Парсинг AI відповіді"""
        hook = ""
        body = ""
        cta = ""
        current_section = None

        for line in content.split('\n'):
            line = line.strip()

            if line.upper().startswith('HOOK:'):
                current_section = 'hook'
                hook = line[5:].strip()
            elif line.upper().startswith('BODY:'):
                current_section = 'body'
                body = line[5:].strip()
            elif line.upper().startswith('CTA:'):
                current_section = 'cta'
                cta = line[4:].strip()
            elif line and current_section:
                if current_section == 'hook':
                    hook += ' ' + line
                elif current_section == 'body':
                    body += ' ' + line
                elif current_section == 'cta':
                    cta += ' ' + line

        full_script = f"{hook}\n\n{body}\n\n{cta}"

        return {
            'hook': hook.strip(),
            'body': body.strip(),
            'cta': cta.strip(),
            'full_script': full_script.strip()
        }

    def _estimate_duration(self, text: str) -> int:
        """Оцінка тривалості"""
        words = len(text.split())
        wps = self.global_settings['words_per_second']
        return int(words / wps)

    def generate_seo_metadata(self, script: Dict) -> Dict:
        """Генерація SEO метаданих"""
        hook = script['hook'][:50]
        niche = script['niche_name']

        title = f"{hook}... | {niche}"
        if len(title) > 100:
            title = title[:97] + "..."

        description = f"""🔥 {script['hook']}

{script['body'][:200]}...

💡 {script['cta']}

🎯 Підписуйся для більше контенту про {niche.lower()}!

#Shorts #{script['niche']} #{script['keywords'][0] if script['keywords'] else 'viral'}
"""

        tags = [
            script['niche'],
            niche,
            'shorts',
            'youtube shorts'
        ] + script['keywords'][:6]

        return {
            'title': title,
            'description': description,
            'tags': tags[:10],
            'category_id': '22'
        }

    def get_daily_stats(self) -> Dict:
        """Статистика у форматі, сумісному з оркестратором."""
        return {
            'provider': self.provider,
            'model': self.groq_model if self.provider == 'groq' else self.provider,
            'tokens_used': 0,
            'daily_cost': 0.0
        }


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    generator = FreeContentGenerator()

    print("\n🆓 FREE Content Generator Test")
    print("="*60)

    script = generator.generate_script(niche_id='motivation')

    print(f"\nНІША: {script['niche_name']}")
    print(f"ТРИВАЛІСТЬ: {script['estimated_duration']} секунд")
    print(f"ПРОВАЙДЕР: {script['metadata']['provider']}")
    print(f"ВАРТІСТЬ: ${script['metadata']['cost']}")
    print("="*60)
    print(f"\nHOOK:\n{script['hook']}")
    print(f"\nBODY:\n{script['body']}")
    print(f"\nCTA:\n{script['cta']}")
    print("\n" + "="*60)

    seo = generator.generate_seo_metadata(script)
    print(f"\nTITLE: {seo['title']}")
    print(f"TAGS: {', '.join(seo['tags'][:5])}")
