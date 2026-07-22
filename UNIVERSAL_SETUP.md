# Universal Reels v12 — коротке налаштування

Проєкт створює один чистий вертикальний MP4 без водяних знаків і готує
окремий підпис для YouTube Shorts, TikTok, Instagram Reels і Facebook Reels.
Помилка одного каналу не зупиняє решту, а MP4 завжди лишається на Dashboard.

## 1. Головні змінні Render

У `Render → Environment` додайте:

```text
AUTO_UPLOAD=True
AUTO_PUBLISH_PLATFORMS=youtube,instagram,facebook,tiktok
PUBLIC_BASE_URL=https://youtube-automation-zoiy.onrender.com
MEDIA_SHARE_SECRET=вставте-довгий-випадковий-рядок
CONTENT_PROFILE=growth
```

- `growth` — 18–35 секунд: краще для тестування тем, утримання й підписників.
- `rewards` — 62–80 секунд: формат, сумісний із вимогою TikTok Creator
  Rewards щодо роликів довше хвилини. Він рендериться довше.

Після зміни змінних натисніть `Save Changes`, дочекайтеся redeploy і перевірте
блок «Канали публікації» на Dashboard.

## 2. YouTube

Поточне підключення через кнопку `Підключити YouTube` лишається без змін.
У списку платформ має бути `youtube`.

## 3. Instagram Reels

Потрібен професійний Instagram-акаунт і Meta-застосунок із дозволом на
публікацію контенту. Додайте в Render:

```text
INSTAGRAM_USER_ID=числовий-id-instagram-акаунта
INSTAGRAM_ACCESS_TOKEN=довгостроковий-meta-token
```

Render тимчасово віддає Meta підписане посилання на конкретний MP4. Інші
файли через нього отримати неможливо.

Офіційна документація: https://developers.facebook.com/docs/instagram-platform/

## 4. Facebook Reels

Потрібна Facebook Page, не особистий профіль. Додайте:

```text
FACEBOOK_PAGE_ID=числовий-id-сторінки
FACEBOOK_PAGE_ACCESS_TOKEN=page-access-token
```

Офіційна документація: https://developers.facebook.com/docs/video-api/guides/reels-publishing/

## 5. TikTok

Для офіційного API потрібен TikTok developer app, Login Kit, Content Posting
API та дозвіл `video.upload` або `video.publish`.

Без аудиту використовуйте безпечний режим Inbox:

```text
TIKTOK_ACCESS_TOKEN=access-token-акаунта
TIKTOK_POST_MODE=inbox
```

Система автоматично відправить відео в TikTok Inbox. У застосунку TikTok треба
відкрити сповіщення й підтвердити фінальний пост.

Повністю прямий публічний пост доступний лише після аудиту TikTok:

```text
TIKTOK_POST_MODE=direct
TIKTOK_DIRECT_POST_APPROVED=True
TIKTOK_PRIVACY_LEVEL=PUBLIC_TO_EVERYONE
```

Не вмикайте ці три змінні до схвалення: неаудитовані клієнти обмежуються
приватними публікаціями. Офіційна документація:
https://developers.tiktok.com/doc/content-posting-api-get-started

## Де реальніше монетизувати

| Платформа | Практичний старт | Роль у системі |
|---|---|---|
| YouTube | Реклама: 1 000 підписників + 10 млн Shorts views/90 днів або 4 000 годин/12 місяців | Головна монетизація |
| TikTok | Creator Rewards: доступний регіон, 10 000 підписників, 100 000 views/30 днів, оригінальні відео від 1 хвилини | Охоплення; `rewards` після доступності програми |
| Instagram | Gifts: професійний акаунт, 18+, щонайменше 500 підписників і підтримувана країна | Бренд, Gifts, майбутні інтеграції |
| Facebook | Stars: 500 підписників протягом 30 днів і підтримувана країна | Додаткове охоплення та Stars |

Умови й країни змінюються. Остаточну доступність перевіряйте в розділах
`Earn/Monetization` самого акаунта.

## Що дасть ріст швидше

1. Публікуйте 3–4 сильні ролики на день, а не 24 майже однакові.
2. Через 30–50 роликів залиште 2–3 ніші з найкращим утриманням і підписками.
3. Перший кадр має одразу показувати конфлікт/дивину; логотип і привітання не потрібні.
4. Робіть оригінальний сценарій, власну озвучку, різні сцени й чесну розв'язку.
5. Не купуйте перегляди та не копіюйте чужі ролики: це шкодить рекомендаціям і монетизації.

