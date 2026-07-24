# Автоматичний запуск і контроль прибутку

## Що запускається автоматично

GitHub Actions тричі на день будить Render і запускає повний цикл:

`тренди/RSS → оригінальний сценарій → переклад ідеї → озвучка → вертикальне відео → YouTube/Instagram/Facebook/TikTok → аналітика`.

Розклад за Києвом:

- 06:05 — органічна tech-ніша;
- 12:05 — anime;
- 18:05 — партнерський tech-ролик, якщо задано `BOT_AFFILIATE_OFFER_ID`; без offer система робить органічний ролик.

Система не імітує перегляди, лайки чи підписки. Це блокує монетизацію і не є прибутком.

## Мінімальна конфігурація

У Render додай змінні з `render-universal.env.example`:

```text
USE_FREE_MODE=True
FREE_TTS_PROVIDER=edge
ENABLE_GLOBAL_SOURCES=True
ANIMATED_BACKGROUNDS=True
AUTO_UPLOAD=True
AUTO_PUBLISH_PLATFORMS=youtube,instagram,facebook,tiktok
PUBLIC_BASE_URL=https://твій-домен.onrender.com
AFFILIATE_FUNNEL_MODE=landing
AUTOMATION_API_TOKEN=довгий_секрет
SECRET_KEY=довгий_секрет
CLICK_HASH_SECRET=довгий_секрет
AFFILIATE_WEBHOOK_SECRET=довгий_секрет
```

Для стабільної БД на Render потрібен Persistent Disk і `DATABASE_PATH=/var/data/youtube_automation.db`. Без диска локальні файли можуть зникнути після перезапуску.

У GitHub Actions додай:

- Secret `AUTOMATION_API_TOKEN` — таке саме значення, як у Render;
- Variable `PUBLIC_BASE_URL` — URL Render;
- Variable `BOT_PROFILE_ID` — профіль каналу;
- Variable `BOT_AFFILIATE_OFFER_ID` — ID дозволеної партнерської пропозиції;
- Variable `AUTO_ROTATE_CONTENT=true` — автоматична ротація слотів;
- за потреби `BOT_ORGANIC_NICHE=tech`, `BOT_ANIME_NICHE=anime`, `BOT_AFFILIATE_NICHE=tech`.

Для кожної активної пропозиції один раз постав у bio/profile URL:
`https://твій-домен.onrender.com/go/<offer_id>`.
Це головний шлях продажу з Reels. `/go/...` показує офер і disclosure, а кнопка
переходу записує реальний affiliate click.

Платформні токени й OAuth заповнюються один раз у профілі/Render. TikTok залишай у `inbox`, доки застосунок не отримає дозвіл на публічний Direct Post.

## Партнерський дохід

В адмінці створи пропозицію з HTTPS-посиланням і власним disclosure. Система автоматично:

1. створює сторінку `/go/<offer_id>` з однією кнопкою переходу;
2. записує клік, платформу, відео і `subid`;
3. додає UTM;
4. приймає підписаний webhook конверсії;
5. рахує confirmed revenue, conversion rate, EPC і profit.

Не збільшуй кількість роликів, якщо немає кліків і підтверджених конверсій. Перевіряй `/api/stats` раз на день. Масштабування має сенс тільки коли `EPC > собівартість одного ролика`.

Бюджет 5 000 грн не витрачай на накрутку, проксі, майнінг і платний трафік до появи EPC. Спочатку використовуй free mode, RSS, Pexels і органічне поширення; гроші залиш на домен, диск і резерв.

## Що прочитати

1. `README.md` — загальна установка.
2. `SECURITY_AND_BOT_SETUP.md` — секрети та GitHub Actions.
3. `PLATFORM_GROWTH_STRATEGY.md` — контент і розподіл.
4. Цей файл — автоматичний режим і гроші.

Правила YouTube: https://support.google.com/youtube/answer/1311392, https://support.google.com/youtube/answer/12504220, https://support.google.com/youtube/answer/72851.
