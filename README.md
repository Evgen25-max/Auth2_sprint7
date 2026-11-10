!
# Auth2 Sprint 7

Проект содержит сервис аутентификации, миграции Alembic, функциональные тесты и инфраструктурные зависимости: PostgreSQL, auth-Redis и rate-limit Redis.

Важно:

- В репозитории должен быть только `.env.example` с безопасными примерами.
- Реальные секреты, пароли и OAuth-клиенты задаются локально или в CI/CD secret store.
- Auth-сервис ожидает доступность критичных зависимостей при старте:
  - PostgreSQL;
  - auth-Redis;
  - rate-limit Redis, если `RATE_LIMIT_ENABLED=true`.

---

## Требования

- Docker Engine;
- Docker Compose v2;
- Доступ к команде `openssl` или любому генератору случайных строк;
- Текстовый редактор, например `nano` или `vim`.

Если Docker требует прав `sudo`, можно использовать `sudo docker compose ...`

---

## Быстрый старт

### 1. Подготовить файл окружения

Из корня репозитория:

```bash
cd etl
cp .env.example .env
nano .env
В файле примере есть поясняющие комментарии

### 2. Настройка Яндекс OAuth
Auth-сервис использует Яндекс OAuth для входа и привязки социальных аккаунтов.
YANDEX_CLIENT_ID=replace-with-yandex-client-id
YANDEX_CLIENT_SECRET=replace-with-yandex-client-secret
YANDEX_REDIRECT_URI=http://127.0.0.1/auth/callback

YANDEX_AUTH_URL=https://oauth.yandex.ru/authorize
YANDEX_TOKEN_URL=https://oauth.yandex.ru/token
YANDEX_INFO_URL=https://login.yandex.ru/info

Порядок настройки:

    Создайте OAuth-приложение в Яндексе.
    Разрешите scopes:
        • Доступ к портрету пользователя
        • Доступ к дате рождения
        • Доступ к адресу электронной почты
        • Доступ к логину, имени и фамилии, полу
        • Доступ к номеру телефона
    Укажите Redirect URI точно так же, как в YANDEX_REDIRECT_URI.
    Скопируйте Client ID и Client Secret в etl/.env.
    Не коммитьте YANDEX_CLIENT_SECRET.

Важно:

    YANDEX_REDIRECT_URI должен совпадать с зарегистрированным в Яндексе URL.
    Для локальной разработки обычно используется http://127.0.0.1:..., а не localhost, если Яндекс требует точного совпадения.
    Реальный callback может быть у фронтенда или gateway, а не у самого auth-сервиса.

### 3. Запуск сервиса
    cd Auth2_sprint7/etl/
    docker compose up -d
    Проверка готовности
    docker compose ps

### 4. Запуск тестов

Функциональные fastapi-movies
cd tests/functional
docker compose --env-file ../../.env up --build --abort-on-container-exit tests

Функциональные auth-service
cd tests/auth_functional
docker compose --env-file ../../.env -f docker-compose.auth.yml up --build --abort-on-container-exit tests

### 5. Остановка сервиса
docker compose down