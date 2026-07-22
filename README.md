# 🚀 Universal Shorts & Reels Automation System

> **v12:** один вертикальний ролик може автоматично розходитися в YouTube
> Shorts, Instagram Reels, Facebook Reels і TikTok. Окремі підписи, ізоляція
> помилок платформ і два профілі тривалості описані в
> [UNIVERSAL_SETUP.md](UNIVERSAL_SETUP.md).
## Повна Інструкція по Встановленню та Запуску

---

## 📋 Зміст

1. [Вимоги](#вимоги)
2. [Швидкий Старт](#швидкий-старт)
3. [Налаштування API Ключів](#налаштування-api-ключів)
4. [Перший Запуск](#перший-запуск)
5. [Deployment](#deployment)
6. [Troubleshooting](#troubleshooting)

---

## Вимоги

### Системні Вимоги:
- Python 3.11 або новіше
- 4GB RAM мінімум (рекомендовано 8GB)
- 10GB вільного місця на диску
- Стабільний інтернет

### Облікові Записи (потрібно створити):
1. ✅ YouTube канал (для публікації)
2. ✅ OpenAI API ключ (або Anthropic Claude)
3. ✅ ElevenLabs акаунт ($5/міс plan)
4. ✅ Pexels API ключ (безкоштовно)
5. ✅ Google Cloud Project (YouTube API)

---

## Швидкий Старт

### 1. Клонування/Завантаження

```bash
# Якщо у вас є git
git clone https://github.com/your-repo/youtube-automation.git
cd youtube-automation

# Або просто розпакуйте ZIP в папку
```

### 2. Віртуальне Середовище

```bash
# Створення venv
python -m venv venv

# Активація (Windows)
venv\Scripts\activate

# Активація (Linux/Mac)
source venv/bin/activate
```

### 3. Встановлення Залежностей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**ВАЖЛИВО:** Якщо moviepy не встановлюється:
```bash
# Спочатку встановіть ffmpeg
# Windows (через chocolatey):
choco install ffmpeg

# Mac:
brew install ffmpeg

# Linux:
sudo apt-get install ffmpeg

# Потім знову:
pip install moviepy
```

### 4. Створення .env Файлу

```bash
# Копіюємо темплейт
cp .env.example .env

# Відкриваємо в редакторі
notepad .env  # Windows
nano .env     # Linux/Mac
```

---

## Налаштування API Ключів

### 1. OpenAI API Key

**Крок 1:** Перейдіть на https://platform.openai.com/api-keys

**Крок 2:** Натисніть "Create new secret key"

**Крок 3:** Скопіюйте ключ (виглядає як `sk-proj-...`)

**Крок 4:** Додайте в `.env`:
```
OPENAI_API_KEY=sk-proj-ваш-ключ-тут
AI_PROVIDER=openai
```

**Крок 5:** Поповніть баланс ($10 хватить на 1-2 місяці)

💡 **Альтернатива:** Claude API (Anthropic)
```
ANTHROPIC_API_KEY=sk-ant-ваш-ключ
AI_PROVIDER=anthropic
```

---

### 2. ElevenLabs API Key

**Крок 1:** Зареєструйтесь на https://elevenlabs.io/

**Крок 2:** Оберіть Starter plan ($5/міс = 30K символів)

**Крок 3:** Перейдіть в Profile → API Keys

**Крок 4:** Додайте в `.env`:
```
ELEVENLABS_API_KEY=ваш-ключ-тут
```

---

### 3. Pexels API Key (Безкоштовно!)

**Крок 1:** Зареєструйтесь на https://www.pexels.com/

**Крок 2:** Перейдіть на https://www.pexels.com/api/

**Крок 3:** Натисніть "Your API Key"

**Крок 4:** Додайте в `.env`:
```
PEXELS_API_KEY=ваш-ключ-тут
```

---

### 4. YouTube API (найскладніше, але важливо!)

**Крок 1:** Перейдіть на https://console.cloud.google.com/

**Крок 2:** Створіть новий проєкт
- Натисніть "Select a project" → "New Project"
- Назва: "YouTube Automation"
- Натисніть "Create"

**Крок 3:** Увімкніть YouTube Data API v3
- В пошуку введіть "YouTube Data API v3"
- Натисніть на API → "Enable"

**Крок 4:** Створіть OAuth 2.0 Credentials
- Перейдіть в "Credentials" (ліва панель)
- Натисніть "Create Credentials" → "OAuth client ID"
- Application type: "Desktop app"
- Name: "YouTube Automation Desktop"
- Натисніть "Create"

**Крок 5:** Завантажте credentials
- Натисніть на створені credentials
- Натисніть "Download JSON"
- **НЕ ЗБЕРІГАЙТЕ цей файл, просто скопіюйте дані!**

**Крок 6:** Додайте в `.env`:
```
YOUTUBE_CLIENT_ID=ваш-client-id.apps.googleusercontent.com
YOUTUBE_CLIENT_SECRET=ваш-secret
YOUTUBE_REDIRECT_URI=http://localhost:5000/oauth2callback
```

**Крок 7:** Налаштування OAuth Consent Screen
- Перейдіть в "OAuth consent screen"
- User Type: External
- App name: "YouTube Automation"
- User support email: ваш-email@gmail.com
- Developer contact: ваш-email@gmail.com
- Scopes: додайте YouTube Data API v3
- Test users: додайте свій email
- Зберегти

**ВАЖЛИВО:** Перший запуск відкриє браузер для авторизації!

---

## Перший Запуск

### Тестування Компонентів

#### 1. Тест Генерації Скриптів
```bash
python src/content_generator.py
```
**Очікуваний результат:**
```
Генерація тестового скрипту...
============================================================
НІША: Мотивація та Mindset
ТРИВАЛІСТЬ: 48 секунд
============================================================

HOOK:
[згенерований текст]

BODY:
[згенерований текст]

CTA:
[згенерований текст]

💰 COST: $0.0023 / $5.00
📊 TOKENS: 412
```

#### 2. Тест Озвучки
```bash
python src/voice_synthesizer.py
```
**Очікуваний результат:**
```
✓ Аудіо створено: output/audio/test_video_001.mp3
  Тривалість: ~15.2s
  Символів: 234
  Голос: Adam
```

#### 3. Тест Рендерингу (якщо є аудіо)
```bash
python src/video_renderer.py
```
**Очікуваний результат:**
```
✓ Відео створено: output/videos/test_render_001.mp4
  Тривалість: 15.1s
  Розмір: 12.4MB
  Час рендерингу: 8.3s
```

#### 4. Тест YouTube Upload
```bash
python src/youtube_uploader.py
```
**Перший запуск відкриє браузер для OAuth авторизації!**

**Очікуваний результат:**
```
📺 Channel Info:
  Назва: Ваш Канал
  Підписників: 0
  Всього переглядів: 0
  Відео: 0

📊 Quota Usage:
  Використано: 0 / 10,000
  Залишилось завантажень: 6
```

---

### Повний Тест Системи

```bash
python src/orchestrator.py
```

**Це створить одне повне відео (без завантаження на YouTube):**

Процес займе 5-10 хвилин:
1. ✅ Генерація скрипту (10-20 сек)
2. ✅ Синтез озвучки (10-30 сек)
3. ✅ Рендеринг відео (3-8 хв)
4. ✅ Збереження в БД

**Результат:**
```
============================================================
✓ TEST COMPLETE
============================================================

Video ID: a3f7b2c1
Path: output/videos/a3f7b2c1.mp4
Duration: 47.3s
Render time: 412.5s
AI cost: $0.0028
File size: 15.2MB
```

---

### Запуск Dashboard

```bash
python -m dashboard.app
```

**Відкрийте в браузері:** http://localhost:5000

Ви побачите:
- 📊 Статистику по відео
- 🎬 Топ відео
- 📅 Розклад генерації
- 🚀 Кнопку для ручної генерації

---

## Автоматизація

### Запуск з Автоматичною Генерацією

```bash
python -m dashboard.app
```

Scheduler автоматично запуститься і буде:
- **03:00 ранку:** Генерувати 3 відео (налаштовується)
- **Кожні 6 годин:** Оновлювати аналітику
- **00:05 ночі:** Оновлювати денну статистику
- **Неділя 02:00:** Очищати старі файли

### Налаштування Розкладу

Відредагуйте `.env`:

```bash
# Скільки відео на день
VIDEOS_PER_DAY=3

# О котрій годині генерувати (24-годинний формат)
GENERATION_TIME=3

# Часовий пояс
TIMEZONE=Europe/Kiev
```

---

## Deployment

### Варіант 1: Railway.app (Рекомендовано)

**Переваги:**
- $5/міс (500 годин)
- Автоматичний deployment з GitHub
- Безкоштовна PostgreSQL БД

**Інструкція:**

1. Створіть акаунт на https://railway.app/

2. Встановіть Railway CLI:
```bash
npm install -g @railway/cli
railway login
```

3. Deploy:
```bash
railway init
railway up
```

4. Додайте Environment Variables:
```bash
railway variables set OPENAI_API_KEY=sk-...
railway variables set ELEVENLABS_API_KEY=...
# ... та інші
```

5. Відкрийте dashboard:
```bash
railway open
```

---

### Варіант 2: Render.com (Безкоштовний Tier)

**Переваги:**
- Безкоштовно (з обмеженнями)
- Автоматичний deployment

**Обмеження:**
- Засинає після 15 хв неактивності
- 750 годин/міс

**Інструкція:**

1. Перейдіть на https://render.com/

2. Створіть новий Web Service

3. Connect до вашого GitHub repo

4. Налаштування:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python -m dashboard.app`

5. Додайте Environment Variables в Render dashboard

---

### Варіант 3: VPS (Найкращий для 24/7)

**Рекомендовані провайдери:**
- DigitalOcean ($6/міс)
- Vultr ($5/міс)
- Hetzner (€4/міс)

**Інструкція:**

```bash
# 1. SSH на сервер
ssh root@ваш-ip

# 2. Встановлення залежностей
apt update
apt install python3-pip python3-venv ffmpeg -y

# 3. Клонування repo
git clone https://github.com/your-repo/youtube-automation.git
cd youtube-automation

# 4. Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Конфігурація
nano .env
# (вставте всі ключі)

# 6. Запуск як сервіс (systemd)
sudo nano /etc/systemd/system/youtube-automation.service
```

**Вміст youtube-automation.service:**
```ini
[Unit]
Description=YouTube Shorts Automation
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/youtube-automation
Environment="PATH=/root/youtube-automation/venv/bin"
ExecStart=/root/youtube-automation/venv/bin/python -m dashboard.app
Restart=always

[Install]
WantedBy=multi-user.target
```

**Запуск:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable youtube-automation
sudo systemctl start youtube-automation
sudo systemctl status youtube-automation
```

---

## Моніторинг та Оптимізація

### Перевірка Логів

```bash
# Останні 100 рядків
tail -n 100 logs/automation.log

# Real-time
tail -f logs/automation.log
```

### Оптимізація Витрат

**Знизити витрати на AI:**
```env
# В .env змініть модель
AI_PROVIDER=openai
# Використовуйте gpt-4o-mini замість gpt-4
```

**Знизити витрати на ElevenLabs:**
```env
# Зменшіть кількість відео
VIDEOS_PER_DAY=2
```

**Відключити автоматичне завантаження (тестування):**
```env
AUTO_UPLOAD=False
TEST_MODE=True
```

---

## Troubleshooting

### Помилка: "No module named 'moviepy'"

**Рішення:**
```bash
pip uninstall moviepy
pip install moviepy==1.0.3
```

Якщо не допомагає:
```bash
# Встановіть ffmpeg
# Windows:
choco install ffmpeg

# Mac:
brew install ffmpeg

# Linux:
sudo apt-get install ffmpeg
```

---

### Помилка: "YouTube API quota exceeded"

**Причина:** Перевищено ліміт 10,000 units/день

**Рішення:**
- Чекайте до наступного дня (00:00 PST)
- Зменшіть VIDEOS_PER_DAY
- Створіть додатковий Google Cloud Project

---

### Помилка: "ElevenLabs character limit exceeded"

**Причина:** Використано всі 30K символів на місяць

**Рішення:**
- Upgrade до вищого плану
- Зменшіть довжину скриптів
- Використовуйте кешування для повторюваних CTA

---

### Відео не завантажуються на YouTube

**Перевірте:**
1. OAuth токен не прострочений:
```bash
rm config/youtube_token.pickle
python src/youtube_uploader.py
```

2. API увімкнено в Google Cloud Console

3. Квота не перевищена

---

### Низька якість відео

**Покращення:**
```env
# В .env
VIDEO_QUALITY=1080
VIDEO_FPS=30
```

Також перевірте що Pexels повертає HD контент.

---

## Масштабування

### Запуск Кількох Каналів

Створіть окремі `.env` файли:
```bash
.env.channel1
.env.channel2
.env.channel3
```

Запустіть окремі інстанси:
```bash
python -m dashboard.app --config .env.channel1 --port 5001
python -m dashboard.app --config .env.channel2 --port 5002
python -m dashboard.app --config .env.channel3 --port 5003
```

---

## Безпека

### ⚠️ НІКОЛИ НЕ КОМІТЬТЕ:
- `.env` файл
- `config/youtube_token.pickle`
- `config/youtube_credentials.json`

**Додайте в .gitignore:**
```
.env
*.pickle
config/credentials.json
output/
*.db
```

---

## Підтримка

**Якщо щось не працює:**

1. Перевірте логи
2. Переконайтесь що всі API ключі правильні
3. Перевірте баланси API (OpenAI, ElevenLabs)
4. Перевірте YouTube квоту

**Корисні команди для debug:**
```bash
# Перевірка версії Python
python --version

# Перевірка встановлених пакетів
pip list

# Тест з verbose логами
python -m src.orchestrator --verbose

# Очистка всього та почати заново
rm -rf output/ *.db config/*.pickle
```

---

## 🎉 Готово!

Тепер ваша система працює 24/7 та автоматично генерує YouTube Shorts!

**Очікування:**
- Місяць 1-2: $100-500/міс
- Місяць 3-4: $500-2,000/міс
- Місяць 5-6: $1,000-5,000/міс

**Удачі! 🚀**
