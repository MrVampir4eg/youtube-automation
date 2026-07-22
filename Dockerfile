# Використовуємо офіційний Python образ
FROM python:3.11-slim

# Встановлюємо системні залежності
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Робоча директорія
WORKDIR /app

# Дозволяє запускати dashboard і імпортувати сусідні пакети src/database
ENV PYTHONPATH=/app

# Копіюємо requirements
COPY requirements.txt .

# Встановлюємо Python залежності
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо весь проект
COPY . .

# Створюємо необхідні директорії
RUN mkdir -p output/videos output/audio output/temp output/video_cache database

# Expose порт
EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import os, requests; requests.get('http://localhost:' + os.getenv('PORT', os.getenv('FLASK_PORT', '5000')) + '/health', timeout=5).raise_for_status()"

# Запуск
CMD ["python", "-m", "dashboard.app"]
