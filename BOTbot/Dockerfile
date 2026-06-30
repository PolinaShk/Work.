FROM python:3.11-slim

WORKDIR /app

# Устанавливаем компиляторы и зависимости для ARM
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    python3-dev \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install python-dateutil

# Копируем код бота
COPY bot/ ./bot/
COPY .env .
COPY logs/ ./logs/

# Создаем папку для логов
RUN mkdir -p logs

ENV PYTHONASYNCIODEBUG=0

# Запускаем бота
CMD ["python", "-m", "bot.main"]