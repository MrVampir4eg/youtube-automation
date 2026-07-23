"""Market-aware free content generator for Ukrainian vertical videos."""

import json
import logging
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

from src.trend_scout import TrendScout


logger = logging.getLogger(__name__)


class FreeContentGenerator:
    """Generate original Shorts/Reels scripts with local quality control."""

    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.together_api_key = os.getenv("TOGETHER_API_KEY", "")

        if self.groq_api_key:
            self.provider = "groq"
            logger.info("✓ Using Groq API (FREE)")
        elif self.together_api_key:
            self.provider = "together"
            logger.info("✓ Using Together AI")
        else:
            self.provider = "fallback"
            logger.warning("⚠ No AI API key found; using original fallback stories")

        config_path = Path(__file__).resolve().parents[1] / "config" / "niches.json"
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as file:
                self.config = json.load(file)
        else:
            logger.warning("Config not found: %s, using defaults", config_path)
            self.config = self._get_default_config()

        self.niches = {item["id"]: item for item in self.config["niches"]}
        self.global_settings = self.config["global_settings"]
        configured = [
            value.strip()
            for value in os.getenv("CONTENT_NICHES", "").split(",")
            if value.strip()
        ]
        safe_defaults = [
            niche_id
            for niche_id, niche in self.niches.items()
            if niche.get("monetization_safe", True)
        ]
        configured_safe = [
            niche_id for niche_id in configured if niche_id in self.niches
        ]
        if configured_safe and os.getenv("AUTO_EXPAND_NICHES", "True").lower() == "true":
            for niche_id in ("mini_stories", "internet_culture"):
                if niche_id in self.niches and niche_id not in configured_safe:
                    configured_safe.append(niche_id)
        self.enabled_niche_ids = configured_safe or safe_defaults or list(self.niches)

        self.target_audience = os.getenv(
            "TARGET_AUDIENCE",
            "україномовні глядачі 18–34 років, які люблять короткий edutainment",
        )
        self.content_profile = os.getenv("CONTENT_PROFILE", "growth").strip().lower()
        if self.content_profile not in {"growth", "rewards"}:
            self.content_profile = "growth"
        self.max_attempts = max(1, min(3, int(os.getenv("SCRIPT_MAX_ATTEMPTS", "2"))))
        self.min_quality_score = max(
            50, min(95, int(os.getenv("MIN_SCRIPT_QUALITY_SCORE", "78")))
        )
        self.trend_scout = TrendScout()
        self.history_path = Path("database/content_history.json")
        self.history_limit = max(20, int(os.getenv("CONTENT_HISTORY_LIMIT", "80")))
        self.history = self._load_history()

    @staticmethod
    def _get_default_config() -> Dict:
        return {
            "niches": [
                {
                    "id": "fun_facts",
                    "name": "Дивні та смішні факти",
                    "keywords": ["facts", "curiosity", "science"],
                    "video_themes": ["surprising discovery"],
                }
            ],
            "global_settings": {
                "min_duration_seconds": 18,
                "max_duration_seconds": 35,
                "words_per_second": 2.5,
            },
        }

    def generate_script(
        self,
        niche_id: Optional[str] = None,
        content_mode: str = "organic",
        affiliate_offer: Optional[Dict] = None,
        channel_name: str = "",
    ) -> Dict:
        content_mode = content_mode if content_mode in {"organic", "affiliate"} else "organic"
        if content_mode == "affiliate" and not affiliate_offer:
            raise ValueError("Для партнерського режиму виберіть партнерську пропозицію")
        niche = self._select_niche(niche_id)
        market_signals = self.trend_scout.get_signals(niche)
        avoid_hooks = [item.get("hook", "") for item in self.history[-10:]]
        logger.info(
            "Generating %s script with %s market signals",
            niche["id"],
            len(market_signals),
        )

        candidates = []
        attempts = 1 if self.provider == "fallback" else self.max_attempts
        for attempt in range(attempts):
            if self.provider == "groq":
                candidate = self._generate_groq(
                    niche, market_signals, avoid_hooks, content_mode,
                    affiliate_offer, channel_name
                )
            elif self.provider == "together":
                candidate = self._generate_together(
                    niche, market_signals, avoid_hooks, content_mode,
                    affiliate_offer, channel_name
                )
            else:
                candidate = self._generate_fallback(
                    niche, content_mode, affiliate_offer
                )

            candidate["quality_score"] = self._score_script(candidate)
            candidate["metadata"]["quality_score"] = candidate["quality_score"]
            candidate["metadata"]["attempt"] = attempt + 1
            candidates.append(candidate)

            if candidate["quality_score"] >= self.min_quality_score:
                break
            avoid_hooks.append(candidate.get("hook", ""))
            logger.info(
                "Draft scored %s/%s; generating a stronger version",
                candidate["quality_score"],
                self.min_quality_score,
            )

        best = max(candidates, key=lambda item: item["quality_score"])
        self._remember(best)
        return best

    def _select_niche(self, niche_id: Optional[str]) -> Dict:
        if niche_id and niche_id in self.niches:
            return self.niches[niche_id]

        choices = [self.niches[item] for item in self.enabled_niche_ids]
        weights = [max(0.1, float(item.get("market_weight", 1.0))) for item in choices]
        return random.choices(choices, weights=weights, k=1)[0]

    def _generate_groq(
        self,
        niche: Dict,
        market_signals: List[str],
        avoid_hooks: List[str],
        content_mode: str = "organic",
        affiliate_offer: Optional[Dict] = None,
        channel_name: str = "",
    ) -> Dict:
        prompt = self._build_prompt(
            niche, market_signals, avoid_hooks, content_mode,
            affiliate_offer, channel_name
        )
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.groq_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Ти український автор коротких відео. Пиши як жива "
                                "людина: конкретно, дотепно, без AI-кліше. Не вигадуй "
                                "факти й не копіюй чужі формулювання."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.88,
                    "max_tokens": 1400 if self.content_profile == "rewards" else 900,
                },
                timeout=35,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return self._build_result(
                niche,
                self._parse_script(content),
                provider="groq",
                model=self.groq_model,
                market_signals=market_signals,
                content_mode=content_mode,
                affiliate_offer=affiliate_offer,
            )
        except Exception as exc:
            logger.error("Groq API error: %s", exc)
            return self._generate_fallback(niche, content_mode, affiliate_offer)

    def _generate_together(
        self,
        niche: Dict,
        market_signals: List[str],
        avoid_hooks: List[str],
        content_mode: str = "organic",
        affiliate_offer: Optional[Dict] = None,
        channel_name: str = "",
    ) -> Dict:
        model = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
        prompt = self._build_prompt(
            niche, market_signals, avoid_hooks, content_mode,
            affiliate_offer, channel_name
        )
        try:
            response = requests.post(
                "https://api.together.xyz/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.together_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Ти український автор коротких вертикальних відео. "
                                "Створюй оригінальні мініісторії без вигаданих фактів."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.88,
                    "max_tokens": 1400 if self.content_profile == "rewards" else 900,
                },
                timeout=35,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return self._build_result(
                niche,
                self._parse_script(content),
                provider="together",
                model=model,
                market_signals=market_signals,
                content_mode=content_mode,
                affiliate_offer=affiliate_offer,
            )
        except Exception as exc:
            logger.error("Together AI error: %s", exc)
            return self._generate_fallback(niche, content_mode, affiliate_offer)

    def _build_result(
        self,
        niche: Dict,
        parsed: Dict,
        provider: str,
        model: str,
        market_signals: Optional[List[str]] = None,
        content_mode: str = "organic",
        affiliate_offer: Optional[Dict] = None,
    ) -> Dict:
        visuals = parsed["visual_queries"] or niche.get("video_themes", ["discovery"])
        return {
            "niche": niche["id"],
            "niche_name": niche["name"],
            "topic": parsed.get("topic") or niche["name"],
            "angle": parsed.get("angle", ""),
            "hook_candidates": parsed.get("hook_candidates", []),
            "hook": parsed["hook"],
            "body": parsed["body"],
            "payoff": parsed["payoff"],
            "loop": parsed.get("loop", ""),
            "cta": parsed["cta"],
            "full_script": parsed["full_script"],
            "estimated_duration": self._estimate_duration(parsed["full_script"]),
            "voice": niche.get("voice", "uk"),
            "keywords": niche.get("keywords", []),
            "video_themes": niche.get("video_themes", ["discovery"]),
            "visual_queries": visuals[:10],
            "on_screen_text": parsed.get("on_screen_text", [])[:4],
            "sound_mood": parsed.get("sound_mood", "curious upbeat"),
            "visual_mode": niche.get("visual_mode", "stock_motion"),
            "animation_style": niche.get("animation_style", "kinetic_captions"),
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "provider": provider,
                "model": model,
                "market_signals": (market_signals or [])[:6],
                "content_profile": self.content_profile,
                "content_mode": content_mode,
                "affiliate_offer": affiliate_offer or None,
                "cost": 0.0,
            },
        }

    def _generate_fallback(
        self,
        niche: Dict,
        content_mode: str = "organic",
        affiliate_offer: Optional[Dict] = None,
    ) -> Dict:
        if content_mode == "affiliate" and affiliate_offer:
            name = str(affiliate_offer.get("name") or "цей сервіс")
            description = str(affiliate_offer.get("description") or "").rstrip(". ")
            parsed = {
                "topic": f"Як спростити задачу через {name}",
                "hook": "Цю рутинну задачу можна скоротити.",
                "body": (
                    f"Замість повторювати все вручну, подивись на {name}. "
                    f"За описом сервісу, він допомагає так: {description}. "
                    "Спочатку перевір безкоштовний режим або демо й порівняй результат "
                    "зі своїм звичним способом."
                ),
                "payoff": "Інструмент корисний лише тоді, коли реально економить твій час.",
                "loop": "Саме тому рутинну задачу варто спочатку виміряти.",
                "cta": affiliate_offer.get("cta") or "Перевір посилання в профілі",
                "angle": "чесна problem-first демонстрація без вигаданих обіцянок",
                "hook_candidates": ["Цю рутинну задачу можна скоротити."],
                "visual_queries": niche.get("video_themes", ["AI software dashboard"]),
                "on_screen_text": ["РУТИНА", name.upper()[:24], "ПЕРЕВІР САМ"],
                "sound_mood": "clean curious",
            }
            parsed["full_script"] = " ".join(
                parsed[key] for key in ("hook", "body", "payoff", "loop")
            )
            return self._build_result(
                niche,
                parsed,
                provider="fallback",
                model="affiliate-template",
                content_mode=content_mode,
                affiliate_offer=affiliate_offer,
            )

        templates = {
            "fun_facts": {
                "topic": "Чому восьминіг воліє ходити",
                "hook": "У восьминога серце зупиняється під час плавання.",
                "body": (
                    "Точніше, головне з трьох сердець перестає качати кров, коли він "
                    "активно пливе. Саме тому повзати дном для нього енергетично вигідніше."
                ),
                "payoff": "Тобто він не ледачий — він економний.",
                "loop": "І так, сердець у нього справді три.",
                "cta": "Ще дивніший факт — завтра",
            },
            "everyday_humor": {
                "topic": "Ранковий будильник",
                "hook": "Будильник зранку — це ділові переговори.",
                "body": (
                    "Перше «відкласти» означає: пропозицію отримано. Друге: потрібен "
                    "час на рішення. Третє: сьогодні наша співпраця неможлива."
                ),
                "payoff": "А потім ти очолюєш відділ запізнень.",
                "loop": "І завтра переговори почнуться знову.",
                "cta": "Надішли сонному другу",
            },
            "psychology": {
                "topic": "Сильна пауза у розмові",
                "hook": "Дві секунди можуть врятувати складну розмову.",
                "body": (
                    "Коли тебе провокують, мозок готує найшвидшу, а не найкращу "
                    "відповідь. Коротка пауза повертає вибір слів і знижує напругу."
                ),
                "payoff": "Контроль — це не мовчання, а правильний момент.",
                "loop": "Іноді відповідь починається саме з паузи.",
                "cta": "Збережи перед розмовою",
            },
            "internet_culture": {
                "topic": "Чому мем стає смішнішим",
                "hook": "Мем стає смішнішим після третього повтору.",
                "body": (
                    "Спочатку ти бачиш жарт. Потім упізнаєш шаблон. А далі вже "
                    "смієшся з того, наскільки безглуздо він знову з'явився."
                ),
                "payoff": "Інтернет називає це культурою. Мама — марнуванням часу.",
                "loop": "Тому цей мем ти ще точно побачиш.",
                "cta": "Який мем не відпускає?",
            },
            "mini_stories": {
                "topic": "Телефон у холодильнику",
                "hook": "Він знайшов телефон у холодильнику.",
                "body": (
                    "П'ять хвилин шукав його з ліхтариком іншого телефона. Уже "
                    "збирався дзвонити оператору, коли захотів води й відкрив дверцята."
                ),
                "payoff": "Телефон охолов. Самооцінка — ні.",
                "loop": "А все почалося з пошуку телефона.",
                "cta": "Було щось подібне?",
            },
            "anime": {
                "topic": "Чому недосконалий герой працює краще",
                "hook": "Ідеальний герой майже завжди нудніший.",
                "body": (
                    "В аніме глядач чіпляється не за силу персонажа, а за його ціну. "
                    "Коли герой помиляється, втрачає час або боїться зробити крок, "
                    "його перемога відчувається заслуженою, а не подарованою сценарієм."
                ),
                "payoff": "Слабкість героя — це не мінус, а двигун історії.",
                "loop": "Тому наступного разу дивись не на силу, а на вибір.",
                "cta": "Який герой це доводить?",
            },
        }
        template = templates.get(niche["id"], templates["fun_facts"])
        parsed = {
            **template,
            "angle": "коротка людська мініісторія",
            "hook_candidates": [template["hook"]],
            "visual_queries": niche.get("video_themes", ["surprised person"]),
            "on_screen_text": ["СТОП", "ОСЬ ЩО ДИВНО", "ФІНАЛ"],
            "sound_mood": "curious playful",
        }
        parsed["full_script"] = " ".join(
            parsed[key] for key in ("hook", "body", "payoff", "loop") if parsed.get(key)
        )
        return self._build_result(
            niche,
            parsed,
            provider="fallback",
            model="original-template",
            content_mode=content_mode,
        )

    def _build_prompt(
        self,
        niche: Dict,
        market_signals: List[str],
        avoid_hooks: List[str],
        content_mode: str = "organic",
        affiliate_offer: Optional[Dict] = None,
        channel_name: str = "",
    ) -> str:
        templates = niche.get("content_templates", [])
        template = random.choice(templates) if templates else {}
        format_name = template.get("type", "curiosity_story")
        structure = template.get(
            "body_structure", "setup → escalation → twist → satisfying payoff"
        )
        market_text = "; ".join(market_signals) or "немає — використай evergreen тему"
        avoid_text = " | ".join(item for item in avoid_hooks if item) or "немає"
        if self.content_profile == "rewards":
            duration_rule = "62–80 секунд, 155–205 слів озвучки"
            pacing_rule = (
                "Після кожних 2–3 речень додай новий поворот; фінал має окупити "
                "хвилину уваги."
            )
        else:
            duration_rule = "18–35 секунд, 50–82 слова озвучки"
            pacing_rule = "Не розтягуй думку: один ролик — одна завершена ідея; візуальний reset кожні 2–3 секунди."

        if content_mode == "affiliate" and affiliate_offer:
            offer_rules = f"""

ПАРТНЕРСЬКИЙ РЕЖИМ:
- Канал: {channel_name or 'вибраний партнерський канал'}
- Сервіс: {affiliate_offer.get('name', '')}
- Перевірений власником опис: {affiliate_offer.get('description', '')}
- Дозволені ключові слова: {', '.join(affiliate_offer.get('keywords', [])) or 'немає'}
- CTA: {affiliate_offer.get('cta') or 'Перевір посилання в профілі'}
- Спочатку покажи реальну проблему й корисний спосіб перевірити сервіс.
- Назви сервіс природно один раз у BODY; ролик не повинен звучати як агресивна реклама.
- Не вигадуй ціну, функції, особистий досвід, заробіток, гарантії, рейтинги або відгуки.
- Не кажи «я користувався/заробив/перевірив», якщо цього немає в описі власника.
- Озвучений CTA може лише чесно сказати, що посилання є в профілі.
"""
        else:
            offer_rules = """

ОРГАНІЧНИЙ РЕЖИМ:
- Не рекламуй, не називай бренди й не проси переходити за посиланням.
- Мета — утримання, коментар або підписка без продажу.
"""

        return f"""Створи ОДИН оригінальний український сценарій для вертикального відео.

КАНАЛ:
- Ніша: {niche['name']}
- Аудиторія: {self.target_audience}
- Формат: {format_name}
- Дуга: {structure}
- Безпечні ринкові сигнали: {market_text}
- Не повторюй попередні хуки: {avoid_text}
{offer_rules}

РИНКОВА ФОРМУЛА:
1. Перша секунда зупиняє свайп: 4–7 простих слів на екрані, без логотипа й привітання.
2. До третьої секунди відкрий інформаційну петлю — глядач має захотіти відповідь.
3. Кожні 1–2 речення додавай нову деталь, контраст або зміну очікування; кадр має оновлюватися кожні 2–3 секунди.
4. Дай чесну розв'язку/панчлайн до фіналу. Остання фраза природно повертає до HOOK.
5. В органічному режимі CTA просить зберегти або надіслати ролик, без вимушених коментарів.
6. У партнерському режимі CTA веде в профіль; disclosure має бути зрозумілим і в ролику, і в підписі.

ЖОРСТКІ ВИМОГИ:
- {duration_rule}
- {pacing_rule}
 - жива розмовна українська; короткі речення; одна доречна іронічна деталь
 - якщо ринковий сигнал іншою мовою, переклади лише ідею українською; не копіюй заголовок або текст джерела
- без привітань, води, моралізаторства, «шок», «ти не повіриш», «99% людей»
- не вигадуй статистику, цитати, дослідження, новини чи особистий досвід
- не давай медичних, юридичних, політичних або фінансових порад
- тренд можна використати лише як безпечний кут, не як джерело фактів
- не копіюй мем, відео або чужий сценарій; створи власну мініісторію
- візуали мають буквально відповідати послідовним сценам, а не бути абстрактними

ФОРМАТ ВІДПОВІДІ — назви секцій не змінюй:

TOPIC:
[конкретна тема, до 8 слів]

ANGLE:
[чому саме цей варіант цікавий]

HOOK_A:
[варіант 1]

HOOK_B:
[варіант 2]

HOOK_C:
[варіант 3]

HOOK:
[найсильніший варіант]

BODY:
[мініісторія з двома attention reset]

PAYOFF:
[чесна відповідь або панчлайн]

LOOP:
[коротка фраза, що з'єднує фінал із HOOK]

CTA:
[2–5 слів для екрана, без благання]

ON_SCREEN:
[3–4 короткі акцентні фрази через кому]

VISUALS:
[8–10 конкретних англомовних stock-video queries через кому, у порядку сюжету]

SOUND_MOOD:
[2–3 англійські слова]
"""

    def _parse_script(self, content: str) -> Dict:
        aliases = {
            "TOPIC": "topic",
            "ANGLE": "angle",
            "HOOK_A": "hook_a",
            "HOOK_B": "hook_b",
            "HOOK_C": "hook_c",
            "HOOK": "hook",
            "BODY": "body",
            "PAYOFF": "payoff",
            "LOOP": "loop",
            "CTA": "cta",
            "ON_SCREEN": "on_screen",
            "VISUALS": "visuals",
            "SOUND_MOOD": "sound_mood",
        }
        sections = {value: "" for value in aliases.values()}
        current = None

        for raw_line in content.splitlines():
            line = raw_line.strip().strip("*#")
            match = re.match(r"^([A-Z_]+)\s*:\s*(.*)$", line, re.IGNORECASE)
            if match and match.group(1).upper() in aliases:
                current = aliases[match.group(1).upper()]
                sections[current] = match.group(2).strip()
            elif line and current:
                sections[current] = f"{sections[current]} {line}".strip()

        hook_candidates = [
            sections[key].strip()
            for key in ("hook_a", "hook_b", "hook_c")
            if sections[key].strip()
        ]
        hook = sections["hook"].strip() or (hook_candidates[0] if hook_candidates else "")
        full_script = " ".join(
            value.strip()
            for value in (
                hook,
                sections["body"],
                sections["payoff"],
                sections["loop"],
            )
            if value.strip()
        )
        visuals = self._split_list(sections["visuals"], limit=10)
        on_screen = self._split_list(sections["on_screen"], limit=4)

        return {
            "topic": sections["topic"].strip(),
            "angle": sections["angle"].strip(),
            "hook_candidates": hook_candidates,
            "hook": hook,
            "body": sections["body"].strip(),
            "payoff": sections["payoff"].strip(),
            "loop": sections["loop"].strip(),
            "cta": sections["cta"].strip(),
            "full_script": full_script,
            "visual_queries": visuals,
            "on_screen_text": on_screen,
            "sound_mood": sections["sound_mood"].strip(),
        }

    @staticmethod
    def _split_list(value: str, limit: int) -> List[str]:
        return [
            item.strip().strip("[]-*•0123456789. ")
            for item in re.split(r"[,;\n]", value)
            if item.strip().strip("[]-*•0123456789. ")
        ][:limit]

    def _score_script(self, script: Dict) -> int:
        score = 0
        hook_words = script.get("hook", "").split()
        total_words = script.get("full_script", "").split()
        body_words = script.get("body", "").split()

        if 4 <= len(hook_words) <= 8:
            score += 20
        elif 3 <= len(hook_words) <= 11:
            score += 10
        if self.content_profile == "rewards":
            ideal_words = 150 <= len(total_words) <= 210
            acceptable_words = 135 <= len(total_words) <= 225
            ideal_body = 115 <= len(body_words) <= 180
        else:
            ideal_words = 45 <= len(total_words) <= 88
            acceptable_words = 35 <= len(total_words) <= 100
            ideal_body = 25 <= len(body_words) <= 65

        if ideal_words:
            score += 18
        elif acceptable_words:
            score += 8
        if ideal_body:
            score += 10
        if script.get("payoff"):
            score += 12
        if script.get("loop"):
            score += 10
        if len(script.get("visual_queries", [])) >= 7:
            score += 10
        if len(script.get("on_screen_text", [])) >= 3:
            score += 5
        if len(script.get("hook_candidates", [])) >= 3:
            score += 5
        if script.get("cta") and len(script["cta"].split()) <= 6:
            score += 5
        if not self._is_duplicate(script.get("hook", "")):
            score += 5

        generic = (
            "ти не повіриш",
            "про це ніхто не говорить",
            "99% людей",
            "шокуючий факт",
            "в сучасному світі",
        )
        lowered = script.get("full_script", "").lower()
        if any(phrase in lowered for phrase in generic):
            score -= 15
        if not script.get("hook") or not script.get("body"):
            score -= 30
        return max(0, min(100, score))

    def _estimate_duration(self, text: str) -> int:
        words = len(text.split())
        words_per_second = float(self.global_settings.get("words_per_second", 2.5))
        return max(1, round(words / words_per_second))

    def _load_history(self) -> List[Dict]:
        try:
            if self.history_path.exists():
                with self.history_path.open("r", encoding="utf-8") as file:
                    data = json.load(file)
                if isinstance(data, list):
                    return data[-self.history_limit :]
        except Exception as exc:
            logger.warning("Could not read content history: %s", exc)
        return []

    def _remember(self, script: Dict) -> None:
        record = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "niche": script.get("niche"),
            "topic": script.get("topic"),
            "hook": script.get("hook"),
            "quality_score": script.get("quality_score"),
        }
        self.history = (self.history + [record])[-self.history_limit :]
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            with self.history_path.open("w", encoding="utf-8") as file:
                json.dump(self.history, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Could not persist content history: %s", exc)

    def _is_duplicate(self, hook: str) -> bool:
        current = set(self._normalised_words(hook))
        if not current:
            return False
        for item in self.history[-20:]:
            previous = set(self._normalised_words(item.get("hook", "")))
            union = current | previous
            if union and len(current & previous) / len(union) >= 0.62:
                return True
        return False

    @staticmethod
    def _normalised_words(value: str) -> List[str]:
        return [
            token
            for token in re.findall(r"[a-zA-Zа-яА-ЯіІїЇєЄґҐ0-9]+", value.lower())
            if len(token) > 2
        ]

    def generate_seo_metadata(self, script: Dict) -> Dict:
        hook = script["hook"].strip().rstrip(".!?")
        topic = script.get("topic") or script["niche_name"]
        title = hook if len(hook) >= 28 else f"{hook} — {topic}"
        title = title[:92].rstrip(" -—")

        description = (
            f"{script['hook']}\n\n"
            f"{script.get('payoff', '')}\n\n"
            f"{script.get('cta', '')}\n\n"
            f"#Shorts #{script['niche']} #українською"
        )
        offer = script.get("metadata", {}).get("affiliate_offer") or {}
        affiliate = None
        if script.get("metadata", {}).get("content_mode") == "affiliate" and offer:
            disclosure = offer.get("disclosure") or (
                "Партнерське посилання: я можу отримати комісію без доплати з вашого боку."
            )
            description = (
                f"{description}\n\n🔗 {offer.get('name')}: {offer.get('url')}"
                f"\n{disclosure}"
            )
            affiliate = {
                "offer_id": offer.get("offer_id"),
                "name": offer.get("name"),
                "url": offer.get("url"),
                "disclosure": disclosure,
                "cta": offer.get("cta") or "Перевір посилання в профілі",
            }
        tags = [
            script["niche"],
            script["niche_name"],
            topic,
            "shorts",
            "українські shorts",
        ] + script.get("keywords", [])[:5]
        return {
            "title": title,
            "description": description,
            "tags": tags[:10],
            "category_id": "22",
            "affiliate": affiliate,
        }

    def get_daily_stats(self) -> Dict:
        return {
            "provider": self.provider,
            "model": self.groq_model if self.provider == "groq" else self.provider,
            "tokens_used": 0,
            "daily_cost": 0.0,
        }


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    generator = FreeContentGenerator()
    result = generator.generate_script(niche_id="fun_facts")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
