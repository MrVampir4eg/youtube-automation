PROFIT PLATFORM v15 — запуск

1. Розпакуй архів.
2. Запусти INSTALL_PROFIT_PLATFORM_V15.cmd від імені користувача з доступом push до GitHub.
3. Інсталятор спочатку створить у GitHub backup-гілку поточного main; лише після цього накладе оновлення.
4. У Render задай змінні з render-universal.env.example.
5. У GitHub Actions задай AUTOMATION_API_TOKEN і PUBLIC_BASE_URL.
6. Один раз створи канал/профіль, токени платформ і дозволену affiliate offer.
7. Залиш AUTO_ROTATE_CONTENT=true.
8. Постав у bio/profile кожного Reels-каналу URL `https://твій-домен.onrender.com/go/<offer_id>`.

Автоматичний розклад: 06:05 tech, 12:05 anime, 18:05 affiliate tech.
Якщо affiliate offer не задана, третій слот стає органічним.

Для TikTok без схвалення Direct Post відео приходить у inbox, не публічно.
Для стабільної історії та кліків на Render потрібен Persistent Disk.

505 — ціль для контролю, не гарантія зовнішньої виплати.
Дохід рахується за підтвердженими конверсіями, а не за переглядами.
Кнопка на `/go/<offer_id>` рахує клік і веде на партнерський checkout.

Читати після запуску:
README.md
SECURITY_AND_BOT_SETUP.md
PLATFORM_GROWTH_STRATEGY.md
PROFIT_FIRST_SETUP.md
MARKET_AND_AUDIENCE_PLAYBOOK.md
