"""
YouTube Shorts Content Generator
Автоматична генерація скриптів через AI (OpenAI або Anthropic)
"""

import os
import json
import random
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import openai
from anthropic import Anthropic
from src.trend_scout import TrendScout

logger = logging.getLogger(__name__)


class ContentGenerator:
    """Генератор контенту для YouTube Shorts"""

    def __init__(self):
        self.provider = os.getenv('AI_PROVIDER', 'openai')

        # Ініціалізація API клієнтів
        if self.provider == 'openai':
            openai.api_key = os.getenv('OPENAI_API_KEY')
            self.model = 'gpt-4o-mini'  # Найдешевший варіант
        elif self.provider == 'anthropic':
            self.client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
            self.model = 'claude-3-5-haiku-20241022'  # Швидкий і дешевий

        # Завантаження конфігурації ніш
        config_path = Path(__file__).resolve().parents[1] / 'config' / 'niches.json'
        with config_path.open('r', encoding='utf-8') as f:
            self.config = json.load(f)

        self.niches = {n['id']: n for n in self.config['niches']}
        self.global_settings = self.config['global_settings']
        self.trend_scout = TrendScout()

        # Лічильники для tracking витрат
        self.tokens_used_today = 0
        self.daily_cost = 0.0

    def select_niche(self, niche_id: Optional[str] = None) -> Dict:
        """Вибір ніші (випадковий або конкретний)"""
        if niche_id and niche_id in self.niches:
            return self.niches[niche_id]

        # Випадковий вибір з активних ніш
        active_niches = list(self.niches.keys())
        return self.niches[random.choice(active_niches)]

    def generate_script(self, niche_id: Optional[str] = None,
                       template_type: Optional[str] = None,
                       content_mode: str = 'organic',
                       affiliate_offer: Optional[Dict] = None,
                       channel_name: str = '') -> Dict:
        """
        Генерація скрипту для відео

        Returns:
            {
                'niche': str,
                'template': str,
                'hook': str,
                'body': str,
                'cta': str,
                'full_script': str,
                'estimated_duration': int,
                'metadata': {...}
            }
        """
        logger.info(f"Генерація скрипту для ніші: {niche_id or 'random'}")

        # Вибір ніші
        niche = self.select_niche(niche_id)

        # Вибір темплейту
        if template_type:
            template = next((t for t in niche['content_templates']
                           if t['type'] == template_type), None)
            if not template:
                template = random.choice(niche['content_templates'])
        else:
            template = random.choice(niche['content_templates'])

        market_signals = self.trend_scout.get_signals(niche)

        # Побудова промпту
        if content_mode == 'affiliate' and not affiliate_offer:
            raise ValueError('Для партнерського режиму виберіть партнерську пропозицію')
        prompt = self._build_prompt(
            niche, template, content_mode, affiliate_offer, channel_name,
            market_signals,
        )

        # Генерація через AI
        if self.provider == 'openai':
            script_data = self._generate_openai(prompt)
        else:
            script_data = self._generate_anthropic(prompt)

        # Парсинг відповіді
        parsed = self._parse_ai_response(script_data)

        # Оцінка тривалості
        estimated_duration = self._estimate_duration(parsed['full_script'])

        result = {
            'niche': niche['id'],
            'niche_name': niche['name'],
            'template': template['type'],
            'hook': parsed['hook'],
            'body': parsed['body'],
            'cta': parsed['cta'],
            'full_script': parsed['full_script'],
            'estimated_duration': estimated_duration,
            'voice': niche['voice'],
            'keywords': niche['keywords'],
            'video_themes': niche['video_themes'],
            'visual_mode': niche.get('visual_mode', 'stock_motion'),
            'animation_style': niche.get('animation_style', 'kinetic_captions'),
            'metadata': {
                'generated_at': datetime.utcnow().isoformat(),
                'provider': self.provider,
                'model': self.model,
                'content_mode': content_mode,
                'affiliate_offer': affiliate_offer or None,
                'market_signals': market_signals[:6],
                'tokens_used': script_data.get('tokens', 0),
                'cost': script_data.get('cost', 0)
            }
        }

        # Перевірка якості
        if not self._quality_check(result):
            logger.warning("Script failed quality check, regenerating...")
            return self.generate_script(
                niche_id, template_type, content_mode, affiliate_offer, channel_name
            )

        logger.info(f"✓ Script generated: {estimated_duration}s, "
                   f"{result['metadata']['tokens_used']} tokens")

        return result

    def _build_prompt(
        self,
        niche: Dict,
        template: Dict,
        content_mode: str = 'organic',
        affiliate_offer: Optional[Dict] = None,
        channel_name: str = '',
        market_signals: Optional[List[str]] = None,
    ) -> str:
        """Побудова промпту для AI"""

        min_dur = self.global_settings['min_duration_seconds']
        max_dur = self.global_settings['max_duration_seconds']
        wps = self.global_settings['words_per_second']

        min_words = int(min_dur * wps)
        max_words = int(max_dur * wps)

        if content_mode == 'affiliate' and affiliate_offer:
            mode_rules = f"""
ПАРТНЕРСЬКИЙ РЕЖИМ:
- Канал: {channel_name or 'вибраний канал'}
- Сервіс: {affiliate_offer.get('name', '')}
- Перевірений опис: {affiliate_offer.get('description', '')}
- Назви сервіс природно один раз і поясни, яку конкретну проблему він вирішує.
- Не вигадуй функції, ціну, власний досвід, прибуток, гарантії чи рейтинги.
- CTA: {affiliate_offer.get('cta') or 'Перевір посилання в профілі'}
"""
        else:
            mode_rules = """
ОРГАНІЧНИЙ РЕЖИМ:
- Не рекламуй бренди та не спрямовуй глядача за зовнішнім посиланням.
"""

        market_text = '; '.join(market_signals or []) or 'немає — використай evergreen тему'
        prompt = f"""Створи захоплюючий скрипт для YouTube Shorts на тему з ніші "{niche['name']}".
{mode_rules}

РИНКОВІ СИГНАЛИ:
- Використай їх лише як ідеї для актуальної теми: {market_text}
- Якщо сигнал іншою мовою, переклади ідею українською.
- Не копіюй заголовок, текст статті, відео або чужий сценарій.
- Додавай власне пояснення, контекст і перевірюваний висновок.

ВИМОГИ:
- Тривалість: {min_dur}-{max_dur} секунд ({min_words}-{max_words} слів)
- Тип контенту: {template['type']}
- Структура: {template['body_structure']}
- Цільова аудиторія: 18-35 років
- Мова: Українська (можна використати англіцизми там де природньо)

СТРУКТУРА:

1. HOOK (перша секунда, 4-7 простих слів):
   - Має МОМЕНТАЛЬНО зупинити свайп; без привітання і логотипа
   - Використовуй конкретний конфлікт, контраст або дивину
   - Приклад формату: {template['hook_template']}

2. BODY ({min_dur-8} секунд, ~{min_words-20} слів):
   - {template['body_structure']}
   - Динамічний темп, короткі речення
   - Факти + емоції
   - Storytelling, не лекція
   - Додавай нову деталь або зміну кадру кожні 2-3 секунди

3. CTA (останні 3-5 секунд, ~10 слів):
   - {template['cta']}
   - Для органічного режиму: збережи або надішли; для affiliate: перевір посилання в профілі

СТИЛЬ:
- Розмовний, але професійний
- Енергійний тон
- Використовуй цифри (вони працюють)
- Уникай: кліше, надто formal мова, затягування

ЗАБОРОНЕНО:
- Копіювання точних фактів без перевірки
- Fake news або дезінформація
- Образливий контент
- Clickbait без substance

ФОРМАТ ВІДПОВІДІ (СТРОГО):

HOOK:
[твій текст тут]

BODY:
[твій текст тут]

CTA:
[твій текст тут]

Створи скрипт ЗАРАЗ:"""

        return prompt

    def _generate_openai(self, prompt: str) -> Dict:
        """Генерація через OpenAI API"""
        try:
            max_tokens = int(os.getenv('MAX_TOKENS_PER_REQUEST', 500))

            response = openai.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Ти експерт-копірайтер для вірусного YouTube Shorts контенту. "
                                  "Твої скрипти завжди захоплюють увагу та тримають до кінця."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=max_tokens,
                temperature=0.9,  # Креативність
                top_p=0.95
            )

            content = response.choices[0].message.content
            tokens = response.usage.total_tokens

            # Розрахунок вартості (GPT-4o-mini pricing)
            cost = (tokens / 1_000_000) * 0.15

            self.tokens_used_today += tokens
            self.daily_cost += cost

            return {
                'content': content,
                'tokens': tokens,
                'cost': cost
            }

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    def _generate_anthropic(self, prompt: str) -> Dict:
        """Генерація через Anthropic Claude API"""
        try:
            max_tokens = int(os.getenv('MAX_TOKENS_PER_REQUEST', 500))

            message = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=0.9,
                system="Ти експерт-копірайтер для вірусного YouTube Shorts контенту. "
                       "Твої скрипти завжди захоплюють увагу та тримають до кінця.",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            content = message.content[0].text

            # Tokens підрахунок для Claude
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens
            total_tokens = input_tokens + output_tokens

            # Claude 3.5 Haiku pricing
            cost = (input_tokens / 1_000_000) * 0.25 + (output_tokens / 1_000_000) * 1.25

            self.tokens_used_today += total_tokens
            self.daily_cost += cost

            return {
                'content': content,
                'tokens': total_tokens,
                'cost': cost
            }

        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise

    def _parse_ai_response(self, response: Dict) -> Dict:
        """Парсинг відповіді від AI"""
        content = response['content']

        # Спроба розпарсити структуру
        lines = content.strip().split('\n')

        hook = ""
        body = ""
        cta = ""
        current_section = None

        for line in lines:
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

        # Якщо парсинг не вдався, спробуємо загальний підхід
        if not (hook and body and cta):
            logger.warning("Failed to parse structured response, using fallback")
            # Перші 2 речення = hook, останні 2 = CTA, решта = body
            sentences = content.split('.')
            if len(sentences) >= 4:
                hook = '. '.join(sentences[:2]) + '.'
                cta = '. '.join(sentences[-2:])
                body = '. '.join(sentences[2:-2]) + '.'
            else:
                # Якщо все зламалось, просто розділимо порівну
                words = content.split()
                third = len(words) // 3
                hook = ' '.join(words[:third])
                body = ' '.join(words[third:2*third])
                cta = ' '.join(words[2*third:])

        full_script = f"{hook}\n\n{body}\n\n{cta}"

        return {
            'hook': hook.strip(),
            'body': body.strip(),
            'cta': cta.strip(),
            'full_script': full_script.strip()
        }

    def _estimate_duration(self, text: str) -> int:
        """Оцінка тривалості на основі кількості слів"""
        words = len(text.split())
        wps = self.global_settings['words_per_second']
        return int(words / wps)

    def _quality_check(self, script: Dict) -> bool:
        """Перевірка якості згенерованого скрипту"""

        # Перевірка тривалості
        duration = script['estimated_duration']
        min_dur = self.global_settings['min_duration_seconds']
        max_dur = self.global_settings['max_duration_seconds']

        if not (min_dur <= duration <= max_dur):
            logger.warning(f"Duration {duration}s out of range [{min_dur}, {max_dur}]")
            return False

        # Перевірка що всі секції присутні
        if not (script['hook'] and script['body'] and script['cta']):
            logger.warning("Missing required sections")
            return False

        # Перевірка заборонених слів
        forbidden = self.config['quality_checks']['forbidden_words']
        full_text = script['full_script'].lower()

        for word in forbidden:
            if word.lower() in full_text:
                logger.warning(f"Contains forbidden word: {word}")
                return False

        # Перевірка мінімальної довжини hook (має бути коротким)
        hook_words = len(script['hook'].split())
        if hook_words > 20:
            logger.warning(f"Hook too long: {hook_words} words")
            return False

        return True

    def generate_seo_metadata(self, script: Dict) -> Dict:
        """Генерація SEO метаданих (title, description, tags)"""

        niche = script['niche_name']
        hook = script['hook'][:50]  # Перші 50 символів hook

        # Генерація title
        title_formats = self.config['seo_templates']['title_formats']
        # Використовуємо hook як основу
        title = f"{hook}... | {niche}"

        # Обрізаємо до 100 символів (YouTube limit)
        if len(title) > 100:
            title = title[:97] + "..."

        # Генерація опису
        desc_template = self.config['seo_templates']['description_template']

        description = f"""🔥 {script['hook']}

{script['body'][:200]}...

💡 {script['cta']}

🎯 Підписуйся для більше контенту про {niche.lower()}!

#Shorts #{script['niche']} #{script['keywords'][0]} #{script['keywords'][1]}
"""
        offer = script.get('metadata', {}).get('affiliate_offer') or {}
        affiliate = None
        if script.get('metadata', {}).get('content_mode') == 'affiliate' and offer:
            disclosure = offer.get('disclosure') or (
                'Партнерське посилання: я можу отримати комісію без доплати з вашого боку.'
            )
            description += (
                f"\n🔗 {offer.get('name')}: {offer.get('url')}\n{disclosure}\n"
            )
            affiliate = {
                'offer_id': offer.get('offer_id'),
                'name': offer.get('name'),
                'url': offer.get('url'),
                'disclosure': disclosure,
                'cta': offer.get('cta') or 'Посилання — в описі',
            }

        # Генерація тегів
        tags = [
            script['niche'],
            niche,
            'shorts',
            'youtube shorts'
        ] + script['keywords'][:6]  # Топ 6 keywords

        # YouTube має ліміт 500 символів для тегів
        tags_str = ', '.join(tags[:10])  # Максимум 10 тегів

        return {
            'title': title,
            'description': description,
            'tags': tags_str.split(', '),
            'category_id': '22',  # People & Blogs
            'affiliate': affiliate,
        }

    def get_daily_stats(self) -> Dict:
        """Статистика використання за сьогодні"""
        max_cost = float(os.getenv('MAX_DAILY_COST', 5.0))

        return {
            'tokens_used': self.tokens_used_today,
            'cost': round(self.daily_cost, 4),
            'max_cost': max_cost,
            'remaining_budget': round(max_cost - self.daily_cost, 4),
            'budget_percent_used': round((self.daily_cost / max_cost) * 100, 1)
        }


if __name__ == '__main__':
    # Тестування
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    generator = ContentGenerator()

    print("Генерація тестового скрипту...")
    script = generator.generate_script(niche_id='motivation')

    print("\n" + "="*60)
    print(f"НІША: {script['niche_name']}")
    print(f"ТРИВАЛІСТЬ: {script['estimated_duration']} секунд")
    print("="*60)
    print(f"\nHOOK:\n{script['hook']}")
    print(f"\nBODY:\n{script['body']}")
    print(f"\nCTA:\n{script['cta']}")
    print("\n" + "="*60)

    # SEO metadata
    seo = generator.generate_seo_metadata(script)
    print(f"\nTITLE: {seo['title']}")
    print(f"TAGS: {', '.join(seo['tags'][:5])}")

    # Stats
    stats = generator.get_daily_stats()
    print(f"\n💰 COST: ${stats['cost']} / ${stats['max_cost']}")
    print(f"📊 TOKENS: {stats['tokens_used']}")
