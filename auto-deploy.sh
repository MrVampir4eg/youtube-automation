#!/bin/bash

# ========================================
# АВТОМАТИЧНИЙ DEPLOYMENT НА RENDER.COM
# ========================================

echo "🚀 YouTube Shorts Automation - Auto Deploy"
echo "=========================================="
echo ""

# Кольори
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}Перевірка файлів...${NC}"

# Перевірка що всі файли на місці
if [ ! -f ".env.production" ]; then
    echo -e "${RED}❌ Файл .env.production не знайдено!${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Всі файли на місці${NC}"
echo ""

# Копіюємо production env
cp .env.production .env

echo -e "${BLUE}📦 Створення GitHub репозиторію...${NC}"
echo ""

# Git ініціалізація
git init
git add .
git commit -m "YouTube Shorts Automation - Production Ready ($USER)"

echo ""
echo -e "${GREEN}✓ Git репозиторій створено${NC}"
echo ""

echo "=========================================="
echo "НАСТУПНІ КРОКИ:"
echo "=========================================="
echo ""
echo "1. Створіть БЕЗКОШТОВНИЙ акаунт на https://render.com/"
echo ""
echo "2. Натисніть 'New +' → 'Web Service'"
echo ""
echo "3. Виберіть 'Deploy from GitHub' або завантажте цю папку"
echo ""
echo "4. Налаштування:"
echo "   Build Command: pip install -r requirements-free.txt"
echo "   Start Command: python -m dashboard.app"
echo "   Instance Type: Free"
echo ""
echo "5. Environment Variables (СКОПІЮЙТЕ ЦІ):"
echo "   ────────────────────────────────────"
cat .env.production | grep -v "^#" | grep -v "^$"
echo "   ────────────────────────────────────"
echo ""
echo "6. Натисніть 'Create Web Service'"
echo ""
echo "7. Чекайте 5-10 хвилин"
echo ""
echo "8. Отримаєте URL типу: https://your-app.onrender.com"
echo ""
echo "=========================================="
echo -e "${GREEN}✅ ГОТОВО!${NC}"
echo "=========================================="
echo ""
echo "💰 Вартість: \$0/міс (БЕЗКОШТОВНО!)"
echo "🎬 Перше відео: о 03:00 завтра"
echo "📊 Dashboard буде доступний за вашим Render URL"
echo ""
echo "Успіхів! 🚀"
