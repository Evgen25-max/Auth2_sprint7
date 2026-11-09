"""Социальные аккаунты и OAuth"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUTH_SCHEMA = op.get_context().opts.get('default_schema_name', 'auth')


def upgrade() -> None:
    # 1. users: hashed_password может быть NULL (для OAuth-пользователей без пароля)
    op.alter_column(
        'users', 'hashed_password',
        existing_type=sa.String(length=255),
        nullable=True,
        schema=AUTH_SCHEMA,
    )

    # 2. users: добавляем email (для связывания по доверенному email)
    op.add_column(
        'users',
        sa.Column('email', sa.String(length=255), nullable=True),
        schema=AUTH_SCHEMA,
    )
    # Частичный уникальный индекс: уникален только среди непустых значений
    op.create_index(
        'uq_users_email_not_null', 'users', ['email'],
        unique=True,
        postgresql_where=sa.text('email IS NOT NULL'),
        schema=AUTH_SCHEMA,
    )

    # 3. Таблица user_social_accounts (один пользователь — много соцсетей)
    op.create_table(
        'user_social_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('external_id', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('avatar_url', sa.Text(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('linked_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['user_id'], [f'{AUTH_SCHEMA}.users.id'],
            name='fk_social_user_id', ondelete='CASCADE',
        ),
        sa.UniqueConstraint(
            'provider', 'external_id', name='uq_social_provider_external_id'
        ),
        schema=AUTH_SCHEMA,
    )
    op.create_index(
        'ix_social_user_provider', 'user_social_accounts',
        ['user_id', 'provider'],
        schema=AUTH_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index('ix_social_user_provider',
                  table_name='user_social_accounts', schema=AUTH_SCHEMA)
    op.drop_table('user_social_accounts', schema=AUTH_SCHEMA)
    op.drop_index('uq_users_email_not_null', table_name='users', schema=AUTH_SCHEMA)
    op.drop_column('users', 'email', schema=AUTH_SCHEMA)
    op.alter_column(
        'users', 'hashed_password',
        existing_type=sa.String(length=255),
        nullable=False,
        schema=AUTH_SCHEMA,
    )