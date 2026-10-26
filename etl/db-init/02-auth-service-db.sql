-- 0. Читаем окружение в psql-переменные
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

-- 1. Все шесть переменных обязательны
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

-- 2. Имена без дефолтов
SELECT :'ENV_AUTH_USER'   AS auth_user,
       :'ENV_AUTH_PASS'   AS auth_pass,
       :'ENV_APP_USER'    AS app_user,
       :'ENV_APP_PASS'    AS app_pass,
       :'ENV_AUTH_DB'     AS auth_db,
       :'ENV_AUTH_SCHEMA' AS auth_schema
\gset

-- 3. Роли
SELECT format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'auth_user', :'auth_pass')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'auth_user')
\gexec

SELECT format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'app_user', :'app_pass')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
\gexec

-- 4. БД
SELECT format('CREATE DATABASE %I OWNER %I', :'auth_db', :'auth_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'auth_db')
\gexec

\connect :auth_db

SELECT format('CREATE SCHEMA IF NOT EXISTS %I', :'auth_schema')
\gexec

SELECT format('SET search_path = %I, public', :'auth_schema')
\gexec

-- 5. Таблица пользователей (С полем is_superuser)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    login VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    token_version INTEGER NOT NULL DEFAULT 1  -- <=== ДОБАВЬТЕ ЭТУ СТРОКУ
);

-- 6. Таблица ролей
CREATE TABLE IF NOT EXISTS roles (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        varchar(100) NOT NULL,
    description text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- 7. Таблица прав доступа
CREATE TABLE IF NOT EXISTS permissions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    codename    varchar(100) NOT NULL,
    name        varchar(255) NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- 8. Связь пользователь <-> роль (m2m)
CREATE TABLE IF NOT EXISTS user_roles (
    user_id    uuid NOT NULL,
    role_id    uuid NOT NULL,
    granted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, role_id)
);

-- 9. Связь роль <-> право (m2m)
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       uuid NOT NULL,
    permission_id uuid NOT NULL,
    granted_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (role_id, permission_id)
);

-- 10. История входов
CREATE TABLE IF NOT EXISTS login_history (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid,
    login      varchar(255) NOT NULL,
    ip_address varchar(45),
    user_agent text,
    success    boolean NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- 11. Ограничения
SELECT format('ALTER TABLE users ADD CONSTRAINT uq_users_login UNIQUE (login)')
WHERE to_regclass('users') IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_users_login')
\gexec

SELECT format('ALTER TABLE roles ADD CONSTRAINT uq_roles_name UNIQUE (name)')
WHERE to_regclass('roles') IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_roles_name')
\gexec

SELECT format('ALTER TABLE permissions ADD CONSTRAINT uq_permissions_codename UNIQUE (codename)')
WHERE to_regclass('permissions') IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_permissions_codename')
\gexec

SELECT format('ALTER TABLE user_roles ADD CONSTRAINT fk_user_roles_user_id '
              'FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE')
WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_user_roles_user_id')
\gexec

SELECT format('ALTER TABLE user_roles ADD CONSTRAINT fk_user_roles_role_id '
              'FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE')
WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_user_roles_role_id')
\gexec

SELECT format('ALTER TABLE role_permissions ADD CONSTRAINT fk_role_permissions_role_id '
              'FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE')
WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_role_permissions_role_id')
\gexec

SELECT format('ALTER TABLE role_permissions ADD CONSTRAINT fk_role_permissions_permission_id '
              'FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE')
WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_role_permissions_permission_id')
\gexec

SELECT format('ALTER TABLE login_history ADD CONSTRAINT fk_login_history_user_id '
              'FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL')
WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_login_history_user_id')
\gexec

-- 12. Индексы
CREATE INDEX IF NOT EXISTS ix_user_roles_role_id ON user_roles (role_id);
CREATE INDEX IF NOT EXISTS ix_role_permissions_permission_id ON role_permissions (permission_id);
CREATE INDEX IF NOT EXISTS ix_login_history_user_id ON login_history (user_id);
CREATE INDEX IF NOT EXISTS ix_login_history_created_at ON login_history (created_at);

-- 13. Базовые роли (только user и admin, superuser не нужен как роль)
INSERT INTO roles (name, description)
VALUES ('user',  'Базовая роль сервиса'),
       ('admin', 'Администратор сервиса')
ON CONFLICT (name) DO NOTHING;

-- 14. Владение
SELECT format('ALTER SCHEMA %I OWNER TO %I', :'auth_schema', :'auth_user')
\gexec

SELECT format('ALTER TABLE %I.%I OWNER TO %I', :'auth_schema', t.tablename, :'auth_user')
FROM pg_tables t
WHERE t.schemaname = :'auth_schema'
\gexec

-- 15. Права приложения
SELECT format('GRANT USAGE ON SCHEMA %I TO %I', :'auth_schema', :'app_user') \gexec
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO %I',
              :'auth_schema', :'app_user')
\gexec

SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I '
    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
    :'auth_user', :'auth_schema', :'app_user')
\gexec
    
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA %I '
    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
    :'auth_schema', :'app_user')
\gexec
    
-- 16. Схема поиска
SELECT format('ALTER ROLE %I SET search_path = %I, public', :'auth_user', :'auth_schema')
\gexec
SELECT format('ALTER ROLE %I SET search_path = %I, public', :'app_user',  :'auth_schema')
\gexec
