# PROFIT MAX — головний manual

Версія: 22.07.2026  
Ціль: побудувати автоматичну Reels-first ферму з максимальною ймовірністю
прибутку, не зламавши чинну систему.

## 0. Що цей manual гарантує, а що ні

Система може автоматично створювати оригінальні ролики, перекладати ідеї,
рендерити вертикальне відео, публікувати його через офіційні інтеграції,
вести глядача через landing, рахувати кліки/конверсії та вибирати офер за EPC.

Ніхто чесно не може гарантувати 505 USD за тиждень або заробіток у перші дні.
На результат впливають охоплення, схвалення акаунтів, якість офера, географія,
платіжні правила й реальні покупки. KPI `505` — контрольна ціль, не обіцянка.

Цей план не використовує накрутку, ботоферми, масовий spam, крадіжку відео,
обхід API, фальшиві відгуки або приховану рекламу. Такі методи дають короткий
шум, але знищують акаунти, партнерські виплати та довгий прибуток.

## 1. Модель грошей: пріоритети

Порядок запуску:

1. Affiliate: найшвидший шлях перевірити, чи дає аудиторія гроші.
2. Прямі спонсорські інтеграції: продавати пакет із 3–10 оригінальних роликів.
3. UGC для брендів: створювати ролики за фіксовану оплату, навіть без великої
   власної аудиторії.
4. Цифрові продукти: чекліст, шаблони, база ідей, мінікурс або пресети.
5. Підписка/спільнота: доступ до добірок, розборів і регулярних матеріалів.
6. Платформна монетизація: YouTube/Meta та інші програми після проходження
   вимог. Це бонус, не основний план першого тижня.

Не змішуй усе в одному ролику. Один ролик має одну головну дію: підписатися,
зберегти, перейти в профіль або купити.

## 2. Архітектура прибутку

`signal → original idea → 3 hooks → short video → platform publish → profile →
/go/<offer_id> → tracked click → partner checkout → approved conversion → EPC`

У системі вже передбачені:

- tech та anime-ротація;
- global RSS як джерело сигналів, а не як джерело для копіювання тексту;
- Reels-native формат: сильна перша секунда, короткі captions, зміни кадру;
- YouTube, Instagram, Facebook і TikTok publishers;
- landing з disclosure і одним CTA;
- affiliate click/conversion webhook;
- статистика revenue, conversion rate, EPC і profit;
- auto-selection офера за підтвердженим EPC;
- backup-гілка перед overlay-оновленням.

## 3. Налаштування безпеки перед запуском

### Render

Додай Persistent Disk і:

```text
DATABASE_PATH=/var/data/youtube_automation.db
```

У змінні Render перенеси значення з `render-universal.env.example`:

```text
USE_FREE_MODE=True
FREE_TTS_PROVIDER=edge
ENABLE_GLOBAL_SOURCES=True
ANIMATED_BACKGROUNDS=True
REELS_NATIVE_MODE=True
SCENE_DURATION_SECONDS=2.4
CAPTION_WORDS=3
AUTO_UPLOAD=True
AUTO_PUBLISH_PLATFORMS=youtube,instagram,facebook,tiktok
PUBLIC_BASE_URL=https://твій-домен.onrender.com
AFFILIATE_FUNNEL_MODE=landing
WEEKLY_REVENUE_TARGET=505
AUTO_SELECT_AFFILIATE_OFFER=True
```

Секрети мають бути довгими випадковими значеннями:

```text
SECRET_KEY
AUTOMATION_API_TOKEN
CLICK_HASH_SECRET
AFFILIATE_WEBHOOK_SECRET
MEDIA_SHARE_SECRET
```

Не надсилай їх у чат і не клади в GitHub-код.

### Сервер без зайвої витрати

#### Рекомендація зараз

Не перенось живу ферму з Render у нічний час. Для швидкого виходу на прибуток
залиш Render як публічний dashboard/webhook, а окремий worker підключай після
перевірки першого трафіку.

Основний вибір: Hetzner Cloud `CX33` у Німеччині або Фінляндії — 4 shared vCPU,
8 GB RAM, 80 GB NVMe. Актуальна ціна після коригування з 15.06.2026 — близько
€8.49/міс без VAT, IPv4 оплачується окремо. Для одного послідовного рендера
вертикального відео та dashboard цього достатньо.

Масштабування:

| Навантаження | Сервер | Рішення |
|---|---|---|
| 1–3 ролики/день | Render + Persistent Disk | мінімум витрат, нічого не переносити |
| 3–10 роликів/день | Hetzner CX33 | worker і FFmpeg, один job за раз |
| багато паралельних jobs | Hetzner CX43 | 8 vCPU, 16 GB RAM, більший запас |

Contabo Cloud VPS 10 офіційно рекламується дешевше та з великим обсягом
ресурсів, але для першого production worker я обираю Hetzner через простішу
схему розгортання, актуальні офіційні характеристики та погодинну оплату.

#### Що замовити

```text
Provider: Hetzner Cloud
Location: Falkenstein або Helsinki
Type: CX33
OS: Ubuntu 24.04 LTS
Disk: 80 GB NVMe; окремий backup після стабілізації
Access: SSH key, без root-пароля
```

Не бери GPU, dedicated CPU або великий сервер до появи EPC. Для цього процесу
основне навантаження — CPU/FFmpeg і RAM, не майнінг та не GPU-обчислення.

#### Після створення VPS

1. Додати SSH key і вимкнути password login.
2. Відкрити тільки SSH, HTTPS і потрібний webhook порт.
3. Встановити Docker Compose, Caddy/Nginx і системні security updates.
4. Зберігати `/var/data` на persistent disk/volume.
5. Залишити один worker job одночасно, щоб не вбивати RAM.
6. Переносити worker тільки після тесту `health → render → publish → webhook`.
7. Не зберігати OAuth/affiliate secrets у репозиторії.

#### Важливе рішення

Сервер не створює прибуток сам. Якщо ролики не дають clicks та approved
conversions, більший VPS лише збільшує витрати. Тому спочатку `CX33`, а не
дорогий dedicated; перехід на `CX43` — тільки коли черга jobs або час рендера
реально заважають заробляти.

### GitHub Actions

Створи secret `AUTOMATION_API_TOKEN` з тим самим значенням, що в Render, і
variables:

```text
PUBLIC_BASE_URL
BOT_PROFILE_ID
BOT_AFFILIATE_OFFER_ID
AUTO_ROTATE_CONTENT=true
BOT_ORGANIC_NICHE=tech
BOT_ANIME_NICHE=anime
BOT_AFFILIATE_NICHE=tech
```

Розклад уже розрахований на Київ: 06:05 tech organic, 12:05 anime reach,
18:05 affiliate tech. Якщо офер не вказаний, третій слот стає organic.

### Платформи

- YouTube: OAuth refresh token і потрібний канал.
- Instagram: Professional account, Facebook Page/Meta app, user ID і Graph API
  access token.
- Facebook: Page ID і Page access token.
- TikTok: developer app і OAuth. Без схвалення Direct Post залишай режим Inbox;
  публічний автоматичний Direct Post потребує дозволу TikTok.

Паролі від акаунтів не потрібні. Підключення робиться через офіційну OAuth-
авторизацію, а секрети вводяться тільки в Render/GitHub Secrets.

## 4. Як правильно аналізувати ринок

### Щоденний цикл

О 1-й половині дня зберігай 10–20 сигналів із:

- YouTube Studio Trends та власних Shorts analytics;
- Instagram Professional Dashboard Best Practices;
- TikTok Creative Center Trends, Top Ads і Keyword Insights;
- RSS новин, HN, NASA, Anime News Network та інших відкритих джерел;
- пошукових підказок і коментарів аудиторії;
- affiliate dashboard: EPC, approved rate, refund rate, payout delay.

Для кожного сигналу записуй:

```text
date, source, country, language, niche, keyword, audience_problem,
possible_offer, 3_hooks, rights_risk, expected_CTA
```

### Оцінка теми

Оціни 0–10 і порахуй:

```text
score = demand*3 + scroll_stop*2 + subscription*2 + monetization*2 + safety*1
```

Публікуй першими теми від 70/100. Високі views без підписок, кліків або
повторних глядачів — це reach, а не прибутковий переможець.

### Ознаки гарної ніші

- проблема зрозуміла за одну фразу;
- є регулярні новини або нові запити;
- можна робити серії, а не одиничні ролики;
- аудиторія купує інструменти, підписки або послуги;
- контент можна створити оригінально та легально;
- офер логічно відповідає темі, а не виглядає як випадкова реклама.

## 5. Контентна матриця

Базова пропорція:

| Тип | Частка | Завдання |
|---|---:|---|
| Reach | 60% | нові люди, shares, saves, перегляди |
| Trust | 25% | доказ користі, порівняння, before/after |
| Sales | 15% | один біль, один доказ, один офер |

### Tech

- AI-інструмент за 30 секунд;
- тест «до/після»;
- A/B: два сервіси для однієї задачі;
- помилка, через яку люди переплачують;
- безкоштовна альтернатива та чесний trade-off.

### Anime

- новини й дати релізів;
- пояснення лору власними словами;
- порівняння персонажів або сезонів;
- «що подивитися, якщо сподобалося X»;
- рейтинги з аргументом, а не голим bait.

Не використовуй випадкові уривки аніме, чужу музику чи watermark. Використовуй
власну графіку, ліцензовані матеріали, public domain або реальний коментар із
доданою цінністю.

## 6. Формула ролика

1. 0–1 секунда: 4–7 слів — конкретний конфлікт або результат.
2. Нуль логотипів та привітань перед hook.
3. У перші 3 секунди — доказ, візуальна зміна або цифра.
4. Новий кадр/деталь кожні 2–3 секунди.
5. Великі captions по 2–3 слова.
6. Одна думка, один payoff, один CTA.
7. Organic CTA: `збережи` / `надішли тому, кому треба`.
8. Affiliate CTA: `посилання в профілі`; disclosure має бути зрозумілим.

На кожну тему генеруй 3 hooks:

```text
A: проблема — «Ти втрачаєш час через це»
B: результат — «Ось як зробити це за 20 секунд»
C: контраст — «Безкоштовний спосіб проти платного»
```

Змінюй одну змінну за раз: hook, перший кадр, довжину або CTA. Інакше не
зрозумієш, що саме дало результат.

## 7. Як набирати підписників

- зроби обіцянку профілю: хто ти, яка користь, як часто виходить;
- створи повторювані серії з назвою та номером;
- закріпи 3 ролики: хто ти, найкращий proof, головна пропозиція;
- відповідай на нормальні коментарі окремими відео;
- став питання, яке допоможе вибрати наступну тему;
- давай безкоштовний чекліст лише якщо він реально готовий;
- один сюжет адаптуй під кожну платформу, але прибирай чужі watermark;
- використовуй collab/duet/remix лише з дозволеним контентом і цінністю;
- перетворюй сильний коментар у наступний ролик;
- не продавай у кожному відео — sales-частка має залишатися меншою.

Підписка виникає з повторюваної користі. Куплені підписники, bait-коментарі,
фальшивий дефіцит, масові DM і спам знижують якість аудиторії та блокують
монетизацію.

## 8. Воронка продажу

У bio/profile кожного каналу постав:

```text
https://твій-домен.onrender.com/go/<offer_id>
```

Landing має містити:

1. конкретну обіцянку офера;
2. 2–3 факти, кому він підходить;
3. короткий disclosure;
4. одну кнопку переходу;
5. відсутність зайвих меню та десяти різних CTA.

`/go/<offer_id>` рахує click, зберігає platform/video/subid, додає UTM і веде
на офіційний checkout. Conversion записуй тільки через партнерський webhook або
перевірений order ID.

## 9. Максимізація affiliate-прибутку

Не вибирай офер лише за найбільшим відсотком комісії. Оціни:

```text
expected_profit = clicks * conversion_rate * approved_commission
                  - content_cost - refunds - payout_risk
```

Перевір перед додаванням:

- HTTPS і реальний checkout;
- географію та мову офера;
- recurring або одноразову комісію;
- cookie window;
- мінімальну виплату та спосіб виплати;
- refund/chargeback policy;
- чи дозволяє партнерка social/Reels traffic;
- чи є API/webhook або хоча б перевірений звіт.

Для двох і більше оферів увімкни після перевірки:

```text
AUTO_SELECT_AFFILIATE_OFFER=true
AFFILIATE_PRIOR_CLICKS=8
AFFILIATE_PRIOR_EPC=0.25
AFFILIATE_EXPLORATION_FACTOR=0.15
```

Алгоритм порівнює підтверджений EPC та дає новим оферам контрольований шанс
тесту. Якщо даних мало, не називай випадковий продаж доказом перемоги.

## 10. Метрики та рішення

Через 24 і 72 години дивись не тільки views:

| Рівень | Метрики | Рішення |
|---|---|---|
| Увага | viewed/stayed, swipe-away, retention | міняти hook/перший кадр |
| Цінність | saves, shares, comments | розвивати тему/серію |
| Аудиторія | profile visits, follows/1k views | переписати bio або CTA |
| Продаж | clicks, conversion rate, EPC | лишити/зупинити офер |
| Гроші | approved revenue, refunds, profit | масштабувати тільки плюс |

Порівнюй із медіаною останніх 10 роликів тієї самої ніші. Переможець — ролик,
який дає кращу комбінацію retention + follows + EPC. Повтори його hook у трьох
нових темах. Слабкий hook зупиняй після двох тестів.

Головні формули:

```text
follow_rate = new_followers / views * 1000
conversion_rate = approved_conversions / clicks * 100
EPC = approved_revenue / clicks
profit = approved_revenue - content_cost - refunds - paid_traffic
```

## 11. Бюджет 5 000 грн

Перший тиждень:

- не витрачати на накрутку, проксі, майнінг або рекламу без EPC;
- оплатити лише домен/диск/резерв, якщо вони реально потрібні;
- залишити запас на помилки та платіжні комісії;
- платний трафік тестувати тільки після органічної конверсії.

Правило paid scale:

```text
maximum_CAC < approved_value_per_customer
```

Починай із маленького ліміту, вимикай кампанію при мінусі, не масштабуй один
випадковий conversion.

## 12. План перших 7 днів

### День 0 — технічний запуск

- Render Persistent Disk;
- env/secrets;
- GitHub Actions;
- OAuth YouTube/Meta/TikTok;
- одна тестова органічна публікація;
- одна approved affiliate offer;
- bio/profile URL.

### День 1 — базові дані

- 3 слоти за розкладом;
- 3 hooks на кожну з двох ніш;
- без paid traffic;
- перевірка publish status і landing click.

### День 2–3 — відсів

- виміряти retention, follows, shares, clicks;
- слабкі hooks зупинити;
- переможців повторити в нових темах;
- перевірити webhook і UTM.

### День 4–5 — довіра

- більше before/after та порівнянь;
- один trust-ролик на кожні два reach;
- перевірити refund/payout умови офера.

### День 6–7 — масштабування

- ввімкнути auto-selection лише з кількома оферами;
- залишити найкращі теми;
- оцінити реальний EPC і profit;
- тільки після плюсової економіки вирішувати про paid traffic або сервер.

## 13. Ранкова перевірка

Перед натисканням Install:

```text
[ ] Live code вже є в GitHub main
[ ] Ручних неперенесених змін на Render немає
[ ] У backup branch є поточний main
[ ] DATABASE_PATH веде на Persistent Disk
[ ] PUBLIC_BASE_URL відкривається по HTTPS
[ ] AUTOMATION_API_TOKEN однаковий у Render/GitHub
[ ] YouTube OAuth працює
[ ] Meta tokens належать потрібному Professional/Page акаунту
[ ] TikTok режим Inbox або Direct Post approved
[ ] Affiliate offer має HTTPS, disclosure і дозволяє social traffic
[ ] У bio стоїть /go/<offer_id>
[ ] Тестовий click видно в статистиці
[ ] Conversion webhook підписаний секретом
[ ] Немає ключів у git або чаті
```

Бери тільки `install_profit_platform_v15_max.zip`. Стару ферму не видаляй.
Інсталятор клонує актуальний GitHub `main`, створює backup-гілку і накладає
тільки файли оновлення. Якщо працюючий код існує лише вручну на Render і не
закомічений у GitHub, спочатку потрібен окремий backup.

## 14. Офіційні джерела

- [YouTube Shorts analytics](https://support.google.com/youtube/answer/12942217)
- [YouTube audience retention](https://support.google.com/youtube/answer/9314415)
- [YouTube monetization policies](https://support.google.com/youtube/answer/1311392)
- [Instagram Best Practices](https://about.fb.com/news/2024/10/best-practices-education-hub-creators-instagram/)
- [TikTok Creative Center](https://ads.tiktok.com/help/article/creative-center)
- [TikTok Trends](https://ads.tiktok.com/help/article/how-to-use-trends)
- [TikTok Direct Post API](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post)
- [FTC influencer disclosures](https://www.ftc.gov/business-guidance/resources/disclosures-101-social-media-influencers)
