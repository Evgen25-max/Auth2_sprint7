"""Сидирование системных прав

Revision ID: 0002
Revises: 0001
Create Date: 2026-01-15 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUTH_SCHEMA = op.get_context().opts.get('default_schema_name', 'auth')

# Системные права: (codename, name)
SYSTEM_PERMISSIONS = [
    ('user.manage', 'Управление пользователями'),
    ('role.manage', 'Управление ролями и правами'),
    ('film.restricted.view', 'Просмотр фильмов с ограниченным доступом'),
]

# Системные роли: (name, description, [codenames прав])
SYSTEM_ROLES = [
    ('user', 'Базовый пользователь', []),
    ('admin', 'Администратор сервиса', [
        'user.manage',
        'role.manage',
        'film.restricted.view',
    ]),
]


def upgrade() -> None:
    # Вставляем права
    for codename, name in SYSTEM_PERMISSIONS:
        op.execute(f"""
            INSERT INTO "{AUTH_SCHEMA}".permissions (codename, name)
            VALUES ('{codename}', '{name}')
            ON CONFLICT (codename) DO NOTHING
        """)

    # Обновляем роли с правами
    for role_name, description, perm_codenames in SYSTEM_ROLES:
        # Обновляем описание
        op.execute(f"""
            UPDATE "{AUTH_SCHEMA}".roles
            SET description = '{description}'
            WHERE name = '{role_name}'
        """)

        # Привязываем права
        for codename in perm_codenames:
            op.execute(f"""
                INSERT INTO "{AUTH_SCHEMA}".role_permissions (role_id, permission_id)
                SELECT r.id, p.id
                FROM "{AUTH_SCHEMA}".roles r
                JOIN "{AUTH_SCHEMA}".permissions p ON p.codename = '{codename}'
                WHERE r.name = '{role_name}'
                ON CONFLICT DO NOTHING
            """)


def downgrade() -> None:
    """Удаляем связи прав с ролями, но не сами роли."""
    for role_name, _, perm_codenames in SYSTEM_ROLES:
        for codename in perm_codenames:
            op.execute(f"""
                DELETE FROM "{AUTH_SCHEMA}".role_permissions
                WHERE role_id IN (
                    SELECT id FROM "{AUTH_SCHEMA}".roles WHERE name = '{role_name}'
                )
                AND permission_id IN (
                    SELECT id FROM "{AUTH_SCHEMA}".permissions WHERE codename = '{codename}'
                )
            """)

    # Удаляем права
    for codename, _ in SYSTEM_PERMISSIONS:
        op.execute(f"""
            DELETE FROM "{AUTH_SCHEMA}".permissions
            WHERE codename = '{codename}'
        """)