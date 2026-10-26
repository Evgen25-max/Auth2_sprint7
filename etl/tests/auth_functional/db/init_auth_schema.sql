-- Инициализация схемы auth для функциональных тестов

CREATE SCHEMA IF NOT EXISTS auth;

SET search_path TO auth, public;

-- Права
CREATE TABLE IF NOT EXISTS permissions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    codename    varchar(100) NOT NULL,
    name        varchar(255) NOT NULL,
    CONSTRAINT uq_permissions_codename UNIQUE (codename)
);

-- Роли
CREATE TABLE IF NOT EXISTS roles (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        varchar(100) NOT NULL,
    description text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_roles_name UNIQUE (name)
);

-- Пользователи
CREATE TABLE IF NOT EXISTS users (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    login           varchar(255) NOT NULL,
    hashed_password varchar(255) NOT NULL,
    first_name      varchar(50),
    last_name       varchar(50),
    is_superuser    boolean NOT NULL DEFAULT false,
    token_version INTEGER NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_users_login UNIQUE (login)
);

-- Пользователь <-> роль
CREATE TABLE IF NOT EXISTS user_roles (
    user_id    uuid NOT NULL,
    role_id    uuid NOT NULL,
    granted_at timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (user_id, role_id),

    CONSTRAINT fk_user_roles_user_id
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_user_roles_role_id
        FOREIGN KEY (role_id)
        REFERENCES roles(id)
        ON DELETE CASCADE
);

-- Роль <-> право
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       uuid NOT NULL,
    permission_id uuid NOT NULL,

    PRIMARY KEY (role_id, permission_id),

    CONSTRAINT fk_role_permissions_role_id
        FOREIGN KEY (role_id)
        REFERENCES roles(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_role_permissions_permission_id
        FOREIGN KEY (permission_id)
        REFERENCES permissions(id)
        ON DELETE CASCADE
);

-- История входов
CREATE TABLE IF NOT EXISTS login_history (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid,
    login      varchar(255) NOT NULL,
    ip_address varchar(45),
    user_agent text,
    success    boolean NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT fk_login_history_user_id
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE SET NULL
);

-- Индексы
CREATE INDEX IF NOT EXISTS ix_users_login
    ON users (login);

CREATE INDEX IF NOT EXISTS ix_roles_name
    ON roles (name);

CREATE INDEX IF NOT EXISTS ix_permissions_codename
    ON permissions (codename);

CREATE INDEX IF NOT EXISTS ix_user_roles_role_id
    ON user_roles (role_id);

CREATE INDEX IF NOT EXISTS ix_role_permissions_permission_id
    ON role_permissions (permission_id);

CREATE INDEX IF NOT EXISTS ix_login_history_user_id
    ON login_history (user_id);

CREATE INDEX IF NOT EXISTS ix_login_history_created_at
    ON login_history (created_at);