#!/bin/bash
# Запуск миграций локально для разработки

set -e

echo "=== Auth Service Migrations ==="
echo ""

# Проверяем переменные
: "${POSTGRES_AUTH_USER:?POSTGRES_AUTH_USER is required}"
: "${POSTGRES_AUTH_PASSWORD:?POSTGRES_AUTH_PASSWORD is required}"
: "${POSTGRES_AUTH_DB:?POSTGRES_AUTH_DB is required}"
: "${POSTGRES_AUTH_SCHEMA:=auth}"

echo "PostgreSQL: ${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}"
echo "Database:   ${POSTGRES_AUTH_DB}"
echo "Schema:     ${POSTGRES_AUTH_SCHEMA}"
echo ""

# Применяем миграции
echo "Running migrations..."
alembic upgrade head

echo ""
echo "=== Migrations completed successfully! ==="