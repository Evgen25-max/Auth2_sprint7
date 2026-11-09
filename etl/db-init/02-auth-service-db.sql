-- Создаём роли, БД и схему для auth-сервиса
-- Выполняется один раз при первом запуске контейнера PostgreSQL

-- 1. Читаем переменные окружения
\set ENV_AUTH_USER ''
\set ENV_AUTH_PASS ''
\set ENV_APP_USER ''
\set ENV_APP_PASS ''
\set ENV_AUTH_DB ''
\set ENV_AUTH_SCHEMA ''

\getenv ENV_AUTH_USER   POSTGRES_AUTH_USER
\getenv ENV_AUTH_PASS   POSTGRES_AUTH_PASSWORD
\getenv ENV_APP_USER    POSTGRES_AUTH_APP_USER
\getenv ENV_APP_PASS    POSTGRES_AUTH_APP_PASSWORD
\getenv ENV_AUTH_DB     POSTGRES_AUTH_DB
\getenv ENV_AUTH_SCHEMA POSTGRES_AUTH_SCHEMA

-- 2. Проверка обязательных переменных
SELECT format(
         'DO $x$ BEGIN RAISE EXCEPTION ''Не заданы переменные окружения: %s'', %L; END $x$',
         missing.names, missing.names
       )
FROM (
    SELECT string_agg(v.name, ', ' ORDER BY v.name) AS names
    FROM (VALUES
        ('POSTGRES_AUTH_USER',         :'ENV_AUTH_USER'),
        ('POSTGRES_AUTH_PASSWORD',     :'ENV_AUTH_PASS'),
        ('POSTGRES_AUTH_APP_USER',     :'ENV_APP_USER'),
        ('POSTGRES_AUTH_APP_PASSWORD', :'ENV_APP_PASS'),
        ('POSTGRES_AUTH_DB',           :'ENV_AUTH_DB'),
        ('POSTGRES_AUTH_SCHEMA',       :'ENV_AUTH_SCHEMA')
    ) AS v(name, val)
    WHERE v.val = ''
) AS missing
WHERE missing.names IS NOT NULL
\gexec

-- 3. Присваиваем переменные
SELECT :'ENV_AUTH_USER'   AS auth_user,
       :'ENV_AUTH_PASS'   AS auth_pass,
       :'ENV_APP_USER'    AS app_user,
       :'ENV_APP_PASS'    AS app_pass,
       :'ENV_AUTH_DB'     AS auth_db,
       :'ENV_AUTH_SCHEMA' AS auth_schema
\gset

-- 4. Создаём роли
SELECT format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'auth_user', :'auth_pass')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'auth_user')
\gexec

SELECT format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'app_user', :'app_pass')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
\gexec

-- 5. Создаём БД (auth_admin = owner)
SELECT format('CREATE DATABASE %I OWNER %I', :'auth_db', :'auth_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'auth_db')
\gexec

-- 6. Подключаемся к БД auth_service_db
\connect :auth_db

-- 7. Создаём схему auth. 
-- ВАЖНО: AUTHORIZATION делает auth_admin владельцем схемы.
-- Это значит, что у auth_admin автоматически будут ВСЕ права на неё
-- (включая создание таблиц, индексов, констрейнтов — всё, что нужно Alembic).
SELECT format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION %I', :'auth_schema', :'auth_user')
\gexec

-- 8. Устанавливаем search_path по умолчанию для обеих ролей
-- Это значит: когда приложение подключается к БД без явного указания схемы,
-- PostgreSQL будет искать таблицы в auth.auth_table, а не в public.auth_table
SELECT format('ALTER ROLE %I SET search_path = %I, public', :'auth_user', :'auth_schema')
\gexec

SELECT format('ALTER ROLE %I SET search_path = %I, public', :'app_user',  :'auth_schema')
\gexec

-- 9. Выдаём полные права на схему пользователю приложения (app_user)
-- app_user не владелец БД, поэтому ему нужны явные права
SELECT format('GRANT ALL PRIVILEGES ON SCHEMA %I TO %I', :'auth_schema', :'app_user')
\gexec

-- 10. Права по умолчанию для будущих таблиц, создаваемых auth_admin
-- Когда auth_admin создаёт таблицу через Alembic, app_user автоматически
-- получает на неё SELECT, INSERT, UPDATE, DELETE
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I '
    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
    :'auth_user', :'auth_schema', :'app_user')
\gexec

-- 11. Права по умолчанию для SEQUENCES (нужно для автоинкрементов)
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I '
    'GRANT ALL PRIVILEGES ON SEQUENCES TO %I',
    :'auth_user', :'auth_schema', :'app_user')
\gexec

-- 12. Права по умолчанию для app_user (если он тоже будет создавать объекты)
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I '
    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
    :'app_user', :'auth_schema', :'app_user')
\gexec

SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I '
    'GRANT ALL PRIVILEGES ON SEQUENCES TO %I',
    :'app_user', :'auth_schema', :'app_user')
\gexec
