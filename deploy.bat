@echo off
echo ============================================
echo YouTube Shorts Automation Deployment
echo ============================================
echo.

REM Перевірка .env файлу
if not exist .env (
    echo [ERROR] Файл .env не знайдено!
    echo Створіть .env файл на основі .env.example
    echo cp .env.example .env
    echo Потім відредагуйте .env та додайте всі API ключі
    pause
    exit /b 1
)

echo Виберіть платформу для deployment:
echo 1] Render.com (БЕЗКОШТОВНО, рекомендовано)
echo 2] Railway.app ($5/міс, найкраща якість)
echo 3] Fly.io (Pay-as-you-go)
echo 4] Локальний Docker
echo.
set /p choice="Ваш вибір (1-4): "

if "%choice%"=="1" goto render
if "%choice%"=="2" goto railway
if "%choice%"=="3" goto flyio
if "%choice%"=="4" goto docker
goto invalid

:render
echo.
echo [OK] Deploying to Render.com...
echo.
echo Інструкції:
echo 1. Перейдіть на https://render.com/
echo 2. Натисніть 'New +' → 'Web Service'
echo 3. Connect ваш GitHub/GitLab репозиторій
echo 4. Налаштування:
echo    - Build Command: pip install -r requirements.txt
echo    - Start Command: python -m dashboard.app
echo    - Instance Type: Free
echo 5. Додайте Environment Variables з вашого .env файлу
echo.
echo Ваші environment variables:
type .env | findstr /V "^#" | findstr /V "^$"
echo.
echo Скопіюйте кожну змінну в Render Environment Variables!
echo.
pause
echo [OK] Deployment на Render запущено!
goto end

:railway
echo.
echo [OK] Deploying to Railway.app...
echo.

REM Перевірка Railway CLI
where railway >nul 2>nul
if %errorlevel% neq 0 (
    echo Встановлюю Railway CLI...
    npm install -g @railway/cli
)

echo Авторизація в Railway...
railway login

echo Ініціалізація проєкту...
railway init

echo Завантаження environment variables...
for /f "usebackq tokens=1,* delims==" %%a in (.env) do (
    if not "%%a"=="" (
        if not "%%a"=="#" (
            echo Setting %%a...
            railway variables set "%%a=%%b"
        )
    )
)

echo Deploying...
railway up

echo.
echo [OK] Deployment на Railway завершено!
railway open
goto end

:flyio
echo.
echo [OK] Deploying to Fly.io...
echo.

REM Перевірка Fly CLI
where flyctl >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Fly CLI не встановлено!
    echo Встановіть з: https://fly.io/docs/hands-on/install-flyctl/
    pause
    exit /b 1
)

echo Авторизація в Fly.io...
flyctl auth login

echo Створення додатку...
flyctl launch --no-deploy

echo Завантаження secrets...
for /f "usebackq tokens=1,* delims==" %%a in (.env) do (
    if not "%%a"=="" (
        if not "%%a"=="#" (
            echo Setting %%a...
            flyctl secrets set "%%a=%%b"
        )
    )
)

echo Deploying...
flyctl deploy

echo.
echo [OK] Deployment на Fly.io завершено!
flyctl open
goto end

:docker
echo.
echo [OK] Локальний Docker deployment...
echo.

REM Перевірка Docker
where docker >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Docker не встановлено!
    echo Встановіть Docker Desktop: https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

echo Building Docker image...
docker-compose build

echo Starting containers...
docker-compose up -d

echo.
echo [OK] Docker контейнери запущено!
echo.
echo Dashboard: http://localhost:5000
echo.
echo Корисні команди:
echo   docker-compose logs -f     # Перегляд логів
echo   docker-compose ps          # Статус контейнерів
echo   docker-compose down        # Зупинити
echo   docker-compose restart     # Перезапустити
goto end

:invalid
echo [ERROR] Невірний вибір!
pause
exit /b 1

:end
echo.
echo ============================================
echo [OK] Deployment завершено!
echo ============================================
echo.
echo Наступні кроки:
echo 1. Перевірте dashboard за URL вище
echo 2. Перегляньте логи щоб переконатись що все працює
echo 3. Перший запуск може зайняти 2-3 хвилини
echo 4. Перше відео згенерується автоматично о 03:00
echo.
echo Успіхів з заробітком!
pause
