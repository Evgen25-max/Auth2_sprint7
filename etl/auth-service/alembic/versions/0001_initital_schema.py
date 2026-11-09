"""Создание схемы auth и всех таблиц

Revision ID: 0001
Revises:
Create Date: 2026-01-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Схема из окружения (дефолт 'auth')
AUTH_SCHEMA = op.get_context().opts.get('default_schema_name', 'auth')


def upgrade() -> None:

    # ----------------------------------------------------------
    # 2. Таблица users
    # ----------------------------------------------------------
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'),
                  nullable=False),
        sa.Column('login', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('first_name', sa.String(length=50), nullable=True),
        sa.Column('last_name', sa.String(length=50), nullable=True),
        sa.Column('is_superuser', sa.Boolean(),
                  server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('token_version', sa.Integer(),
                  server_default=sa.text('1'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema=AUTH_SCHEMA,
    )
    op.create_unique_constraint(
        'uq_users_login', 'users', ['login'], schema=AUTH_SCHEMA
    )

    # ----------------------------------------------------------
    # 3. Таблица roles
    # ----------------------------------------------------------
    op.create_table(
        'roles',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'),
                  nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema=AUTH_SCHEMA,
    )
    op.create_unique_constraint(
        'uq_roles_name', 'roles', ['name'], schema=AUTH_SCHEMA
    )

    # ----------------------------------------------------------
    # 4. Таблица permissions
    # ----------------------------------------------------------
    op.create_table(
        'permissions',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'),
                  nullable=False),
        sa.Column('codename', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema=AUTH_SCHEMA,
    )
    op.create_unique_constraint(
        'uq_permissions_codename', 'permissions', ['codename'],
        schema=AUTH_SCHEMA
    )

    # ----------------------------------------------------------
    # 5. Таблица user_roles (M2M)
    # ----------------------------------------------------------
    op.create_table(
        'user_roles',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('granted_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('user_id', 'role_id'),
        schema=AUTH_SCHEMA,
    )
    op.create_foreign_key(
        'fk_user_roles_user_id', 'user_roles', 'users',
        ['user_id'], ['id'],
        source_schema=AUTH_SCHEMA, referent_schema=AUTH_SCHEMA,
        ondelete='CASCADE',
    )
    op.create_foreign_key(
        'fk_user_roles_role_id', 'user_roles', 'roles',
        ['role_id'], ['id'],
        source_schema=AUTH_SCHEMA, referent_schema=AUTH_SCHEMA,
        ondelete='CASCADE',
    )
    op.create_index(
        'ix_user_roles_role_id', 'user_roles', ['role_id'],
        schema=AUTH_SCHEMA,
    )

    # ----------------------------------------------------------
    # 6. Таблица role_permissions (M2M)
    # ----------------------------------------------------------
    op.create_table(
        'role_permissions',
        sa.Column('role_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('permission_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('granted_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('role_id', 'permission_id'),
        schema=AUTH_SCHEMA,
    )
    op.create_foreign_key(
        'fk_role_permissions_role_id', 'role_permissions', 'roles',
        ['role_id'], ['id'],
        source_schema=AUTH_SCHEMA, referent_schema=AUTH_SCHEMA,
        ondelete='CASCADE',
    )
    op.create_foreign_key(
        'fk_role_permissions_permission_id', 'role_permissions', 'permissions',
        ['permission_id'], ['id'],
        source_schema=AUTH_SCHEMA, referent_schema=AUTH_SCHEMA,
        ondelete='CASCADE',
    )
    op.create_index(
        'ix_role_permissions_permission_id', 'role_permissions',
        ['permission_id'], schema=AUTH_SCHEMA,
    )

    # ----------------------------------------------------------
    # 7. Таблица login_history
    # ----------------------------------------------------------
    op.create_table(
        'login_history',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'),
                  nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('login', sa.String(length=255), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema=AUTH_SCHEMA,
    )
    op.create_foreign_key(
        'fk_login_history_user_id', 'login_history', 'users',
        ['user_id'], ['id'],
        source_schema=AUTH_SCHEMA, referent_schema=AUTH_SCHEMA,
        ondelete='SET NULL',
    )
    op.create_index(
        'ix_login_history_user_id', 'login_history', ['user_id'],
        schema=AUTH_SCHEMA,
    )
    op.create_index(
        'ix_login_history_created_at', 'login_history', ['created_at'],
        schema=AUTH_SCHEMA,
    )

    # ----------------------------------------------------------
    # 8. Сидирование базовых ролей
    # ----------------------------------------------------------
    op.execute(f"""
        INSERT INTO "{AUTH_SCHEMA}".roles (name, description)
        VALUES ('user',  'Базовая роль сервиса'),
               ('admin', 'Администратор сервиса')
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    """Откат: удаляем все таблицы и схему."""
    op.drop_index('ix_login_history_created_at',
                  table_name='login_history', schema=AUTH_SCHEMA)
    op.drop_index('ix_login_history_user_id',
                  table_name='login_history', schema=AUTH_SCHEMA)
    op.drop_table('login_history', schema=AUTH_SCHEMA)

    op.drop_index('ix_role_permissions_permission_id',
                  table_name='role_permissions', schema=AUTH_SCHEMA)
    op.drop_table('role_permissions', schema=AUTH_SCHEMA)

    op.drop_index('ix_user_roles_role_id',
                  table_name='user_roles', schema=AUTH_SCHEMA)
    op.drop_table('user_roles', schema=AUTH_SCHEMA)

    op.drop_table('permissions', schema=AUTH_SCHEMA)
    op.drop_table('roles', schema=AUTH_SCHEMA)
    op.drop_table('users', schema=AUTH_SCHEMA)

    # Схему не удаляем — могут быть другие объекты