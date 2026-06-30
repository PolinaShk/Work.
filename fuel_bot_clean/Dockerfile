FROM python:3.10-slim

WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY api_helper.py .
COPY bot.py .
COPY config.py .

# Запускаем бота
CMD ["python", "bot.py"]