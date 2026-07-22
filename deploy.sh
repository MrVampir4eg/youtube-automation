#!/bin/bash

echo "============================================"
echo "🚀 YouTube Shorts Automation Deployment"
echo "============================================"
echo ""

# Кольори для виводу
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Перевірка чи .env файл існує
if [ ! -f .env ]; then
    echo -e "${RED}❌ Файл .env не знайдено!${NC}"
    echo "Створіть .env файл на основі .env.example"
    echo "cp .env.example .env"
    echo "Потім відредагуйте .env та додайте всі API ключі"
    exit 1
fi

echo -e "${BLUE}Виберіть платформу для deployment:${NC}"
echo "1) Render.com (БЕЗКОШТОВНО, рекомендовано)"
echo "2) Railway.app (\$5/міс, найкраща якість)"
echo "3) Fly.io (Pay-as-you-go)"
echo "4) Локальний Docker"
echo ""
read -p "Ваш вибір (1-4): " choice

case $choice in
    1)
        echo -e "${GREEN}🎯 Deploying to Render.com...${NC}"
        echo ""
        echo "📝 Інструкції:"
        echo "1. Перейдіть на https://render.com/"
        echo "2. Натисніть 'New +' → 'Web Service'"
        echo "3. Connect ваш GitHub/GitLab репозиторій"
        echo "4. Налаштування:"
        echo "   - Build Command: pip install -r requirements.txt"
        echo "   - Start Command: python -m dashboard.app"
        echo "   - Instance Type: Free"
        echo "5. Додайте Environment Variables з вашого .env файлу"
        echo ""
        echo -e "${BLUE}Ваші environment variables:${NC}"
        cat .env | grep -v "^#" | grep -v "^$"
        echo ""
        echo "Скопіюйте кожну змінну в Render Environment Variables!"
        echo ""
        read -p "Натисніть Enter коли закінчите налаштування на Render..."
        echo -e "${GREEN}✅ Deployment на Render запущено!${NC}"
        ;;

    2)
        echo -e "${GREEN}🚂 Deploying to Railway.app...${NC}"
        echo ""

        # Перевірка чи Railway CLI встановлено
        if ! command -v railway &> /dev/null; then
            echo "📦 Встановлюю Railway CLI..."
            npm install -g @railway/cli
        fi

        echo "🔐 Авторизація в Railway..."
        railway login

        echo "🚀 Ініціалізація проєкту..."
        railway init

        echo "📤 Завантаження environment variables..."
        # Завантажуємо кожну змінну з .env
        while IFS='=' read -r key value; do
            # Пропускаємо коментарі та пусті рядки
            if [[ ! $key =~ ^# ]] && [[ -n $key ]]; then
                echo "Setting $key..."
                railway variables set "$key=$value"
            fi
        done < .env

        echo "🚀 Deploying..."
        railway up

        echo ""
        echo -e "${GREEN}✅ Deployment на Railway завершено!${NC}"
        railway open
        ;;

    3)
        echo -e "${GREEN}✈️  Deploying to Fly.io...${NC}"
        echo ""

        # Перевірка чи Fly CLI встановлено
        if ! command -v flyctl &> /dev/null; then
            echo "📦 Встановлюю Fly CLI..."
            curl -L https://fly.io/install.sh | sh
        fi

        echo "🔐 Авторизація в Fly.io..."
        flyctl auth login

        echo "🚀 Створення додатку..."
        flyctl launch --no-deploy

        echo "📤 Завантаження secrets..."
        while IFS='=' read -r key value; do
            if [[ ! $key =~ ^# ]] && [[ -n $key ]]; then
                echo "Setting $key..."
                flyctl secrets set "$key=$value"
            fi
        done < .env

        echo "🚀 Deploying..."
        flyctl deploy

        echo ""
        echo -e "${GREEN}✅ Deployment на Fly.io завершено!${NC}"
        flyctl open
        ;;

    4)
        echo -e "${GREEN}🐳 Локальний Docker deployment...${NC}"
        echo ""

        # Перевірка чи Docker встановлено
        if ! command -v docker &> /dev/null; then
            echo -e "${RED}❌ Docker не встановлено!${NC}"
            echo "Встановіть Docker Desktop: https://www.docker.com/products/docker-desktop"
            exit 1
        fi

        echo "🔨 Building Docker image..."
        docker-compose build

        echo "🚀 Starting containers..."
        docker-compose up -d

        echo ""
        echo -e "${GREEN}✅ Docker контейнери запущено!${NC}"
        echo ""
        echo "📊 Dashboard: http://localhost:5000"
        echo ""
        echo "Корисні команди:"
        echo "  docker-compose logs -f     # Перегляд логів"
        echo "  docker-compose ps          # Статус контейнерів"
        echo "  docker-compose down        # Зупинити"
        echo "  docker-compose restart     # Перезапустити"
        ;;

    *)
        echo -e "${RED}❌ Невірний вибір!${NC}"
        exit 1
        ;;
esac

echo ""
echo "============================================"
echo -e "${GREEN}✅ Deployment завершено!${NC}"
echo "============================================"
echo ""
echo "📝 Наступні кроки:"
echo "1. Перевірте dashboard за URL вище"
echo "2. Перегляньте логи щоб переконатись що все працює"
echo "3. Перший запуск може зайняти 2-3 хвилини"
echo "4. Перше відео згенерується автоматично о 03:00"
echo ""
echo "🎉 Успіхів з заробітком!"
