FROM python:3.12

WORKDIR /opt/app

RUN groupadd -r web && useradd -r -g web web

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python зависимости
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходники
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY wait-for-postgres.py .

# Делаем скрипт исполняемым
RUN chmod +x wait-for-postgres.py

# === ГАРАНТИРОВАННО СОЗДАЁМ ПАПКУ ДЛЯ ЛОГОВ ===
RUN mkdir -p /opt/app/logs

# Переменные окружения
ENV PYTHONPATH=/opt/app/src
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8001

# Команда по умолчанию (убрали дублирующуюся строку CMD)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]