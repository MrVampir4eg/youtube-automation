# 🚀 ШВИДКИЙ DEPLOYMENT GUIDE
## Розгортання за 10 хвилин!

**Дата:** 22 липня 2026, 08:58 (Київ)

---

## 🎯 Найкращий варіант для початку: **Render.com (БЕЗКОШТОВНО!)**

### Чому Render?
✅ **Повністю безкоштовний старт**
✅ Автоматичний deployment з Git
✅ Вбудована PostgreSQL БД (якщо потрібно)
✅ Автоматичні SSL сертифікати
✅ Простий у налаштуванні

### Обмеження безкоштовного tier:
- Засинає після 15 хв неактивності
- 750 годин/місяць (достатньо!)
- Обмежена RAM (512MB)

**Для 24/7 роботи:** Upgrade до Starter ($7/міс) коли почнете заробляти

---

## 📝 КРОК ЗА КРОКОМ

### Крок 1: Підготовка проекту (2 хв)

```bash
# 1. Створіть .env файл
cp .env.example .env

# 2. Відредагуйте .env та додайте ваші API ключі:
# - OPENAI_API_KEY=sk-...
# - ELEVENLABS_API_KEY=...
# - PEXELS_API_KEY=...
# - YOUTUBE_CLIENT_ID=...
# - YOUTUBE_CLIENT_SECRET=...
```

**ВАЖЛИВО:** Без цих ключів система не запуститься!

---

### Крок 2: Завантажте на GitHub (3 хв)

```bash
# Ініціалізуйте git (якщо ще не зробили)
git init

# Додайте файли
git add .

# Commit
git commit -m "Initial commit - YouTube Shorts Automation"

# Створіть репозиторій на GitHub.com
# Потім:
git remote add origin https://github.com/ВАШ_USERNAME/youtube-automation.git
git branch -M main
git push -u origin main
```

**⚠️ Не забудьте додати .env в .gitignore!**

---

### Крок 3: Deployment на Render.com (5 хв)

**3.1. Реєстрація**
1. Перейдіть на https://render.com/
2. Sign Up (можна через GitHub)
3. Підтвердіть email

**3.2. Створення Web Service**
1. Натисніть **"New +"** → **"Web Service"**
2. **Connect Repository:**
   - Натисніть "Connect GitHub"
   - Виберіть ваш репозиторій `youtube-automation`
3. **Налаштування:**
   ```
   Name: youtube-shorts-automation
   Region: Frankfurt (найближчий до України)
   Branch: main
   Runtime: Python 3
   Build Command: pip install -r requirements.txt
   Start Command: python -m dashboard.app
   Instance Type: Free
   ```
4. Натисніть **"Create Web Service"**

**3.3. Додавання Environment Variables**
1. В дашборді вашого сервісу → **Environment**
2. Додайте кожну змінну з вашого `.env`:

```
OPENAI_API_KEY = sk-proj-...
ELEVENLABS_API_KEY = ...
PEXELS_API_KEY = ...
YOUTUBE_CLIENT_ID = ...apps.googleusercontent.com
YOUTUBE_CLIENT_SECRET = ...
YOUTUBE_REDIRECT_URI = https://ваш-сервіс.onrender.com/oauth2callback

# Інші важливі
FLASK_PORT = 5000
FLASK_DEBUG = False
DATABASE_URL = sqlite:///youtube_automation.db
TIMEZONE = Europe/Kiev
VIDEOS_PER_DAY = 3
GENERATION_TIME = 3
AUTO_UPLOAD = True
SECRET_KEY = [згенеруйте випадковий ключ]
```

**Як згенерувати SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

3. Натисніть **"Save Changes"**

**3.4. Перший Deploy**
- Render автоматично почне деплой
- Процес займе ~5-10 хвилин
- Слідкуйте за логами в розділі **"Logs"**

**3.5. Перевірка**
1. Коли deploy завершиться, копіюйте URL (щось на кшталт `https://youtube-shorts-automation.onrender.com`)
2. Відкрийте в браузері
3. Ви побачите Dashboard! 🎉

---

## 🔧 Налаштування після deployment

### YouTube OAuth (ОБОВ'ЯЗКОВО!)

Перший раз коли система спробує завантажити відео на YouTube, потрібна авторизація:

1. **Оновіть YOUTUBE_REDIRECT_URI:**
   ```
   https://ваш-сервіс.onrender.com/oauth2callback
   ```

2. **Додайте його в Google Cloud Console:**
   - Перейдіть на https://console.cloud.google.com/
   - Credentials → Edit OAuth client
   - Authorized redirect URIs → Add URI:
     ```
     https://ваш-сервіс.onrender.com/oauth2callback
     ```
   - Save

3. **Перша авторизація:**
   - Система автоматично перенаправить вас для авторизації
   - Підтвердіть доступ до YouTube каналу
   - Token збережеться автоматично

---

## 🎬 Перший запуск

### Ручна генерація тестового відео:

1. Відкрийте Dashboard: `https://ваш-сервіс.onrender.com`
2. Виберіть нішу (наприклад, "Мотивація")
3. Натисніть **"Згенерувати відео"**
4. Зачекайте 5-10 хвилин
5. Перевірте результат в розділі "Топ відео"

### Автоматична генерація:

Система автоматично згенерує відео **о 03:00 ранку (за вашим часовим поясом)**

Щоб змінити час:
```env
GENERATION_TIME=6  # 06:00 ранку
```

---

## 📊 Моніторинг

### Перегляд логів:
1. В Render Dashboard → Logs
2. Шукайте повідомлення:
   ```
   ✓ Video uploaded: abc123xyz
   URL: https://youtube.com/shorts/abc123xyz
   ```

### Перевірка статусу:
- Health check: `https://ваш-сервіс.onrender.com/health`
- API stats: `https://ваш-сервіс.onrender.com/api/stats`

---

## 💰 Очікувані витрати

### Перший місяць (безкоштовно на Render):
```
Хостинг: $0 (Free tier)
OpenAI API: ~$30-50
ElevenLabs: $5
Pexels: $0 (безкоштовно)
YouTube API: $0 (безкоштовно)
---
Разом: ~$35-55/міс
```

### Коли upgrade до платного (після перших $100+ доходу):
```
Render Starter: $7/міс
OpenAI: $50/міс
ElevenLabs: $5-11/міс
---
Разом: $62-68/міс
```

**ROI:** Після 3-4 місяців очікуваний дохід $500-2,000/міс

---

## 🚨 Troubleshooting

### "Application failed to respond"
**Причина:** Холодний старт на Free tier
**Рішення:** Зачекайте 30-60 сек, Render розбудить сервіс

### "Database is locked"
**Причина:** SQLite не підходить для concurrent writes
**Рішення:** 
```bash
# В Render додайте PostgreSQL
# Змініть DATABASE_URL на postgres://...
```

### "YouTube API quota exceeded"
**Причина:** Перевищено 10,000 units/день
**Рішення:** 
- Зменшіть VIDEOS_PER_DAY
- Чекайте до наступного дня (00:00 PST)

### "ElevenLabs character limit"
**Причина:** Використано 30K символів
**Рішення:**
- Upgrade план
- Зменшіть кількість відео

---

## 🔥 Альтернативні хостинги

### Railway.app ($5/міс, найкращий!)

**Переваги:**
- Не засинає
- 500 годин/міс
- Швидший за Render

**Deployment:**
```bash
# Встановіть Railway CLI
npm install -g @railway/cli

# Login
railway login

# Deploy
railway init
railway up

# Додайте environment variables
railway variables set OPENAI_API_KEY=sk-...
railway variables set ELEVENLABS_API_KEY=...
# ... інші
```

---

### Fly.io (Pay-as-you-go)

**Переваги:**
- Платите тільки за використання
- Дуже швидкий
- Глобальна мережа

**Deployment:**
```bash
# Встановіть Fly CLI
curl -L https://fly.io/install.sh | sh

# Login
flyctl auth login

# Deploy
flyctl launch
flyctl deploy
```

---

## 📈 Масштабування

### Коли досягнете $1,000/міс:

1. **Upgrade хостинг:**
   - Render Professional ($25/міс)
   - Або VPS (DigitalOcean $12/міс)

2. **Запустіть кілька каналів:**
   - 3-5 різних ніш
   - Окремі YouTube канали
   - Різні облікові записи

3. **Збільште генерацію:**
   ```env
   VIDEOS_PER_DAY=5-10
   ```

4. **Додайте аналітику:**
   - Google Analytics
   - Custom dashboards
   - A/B testing ніш

---

## ✅ Checklist перед deployment

- [ ] Всі API ключі додані в .env
- [ ] .env НЕ закомічений в Git
- [ ] YouTube OAuth налаштовано
- [ ] Репозиторій на GitHub створено
- [ ] Render.com акаунт створено
- [ ] Environment variables додані на Render
- [ ] Перший deploy успішний
- [ ] Dashboard відкривається
- [ ] Логи показують "Scheduler running"

---

## 🎉 Готово!

Ваша система тепер працює 24/7 та автоматично генерує YouTube Shorts!

**Очікування:**
- **Перше відео:** сьогодні о 03:00 (або manual generation)
- **Перші $100:** за 6-8 тижнів
- **Перші $1,000:** за 3-4 місяці

**Підтримка:**
- Перевіряйте Dashboard щодня перші 2 тижні
- Аналізуйте які відео viral (копіюйте формат)
- Коригуйте ніші based on performance

---

**Успіхів! 🚀💰**

*Створено: 22.07.2026, 08:58 (Київ)*
