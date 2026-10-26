
import uuid
from datetime import datetime

from db.postgres import Base
from sqlalchemy import (Boolean, DateTime, ForeignKey, String, Text, text,
                        UniqueConstraint, func, Integer)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

SCHEMA = 'auth'


class User(Base):
    """Пользователь сервиса."""

    __tablename__ = 'users'
    __table_args__ = (
        UniqueConstraint('login', name='uq_users_login'),
        {'schema': SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    login: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(50))
    last_name: Mapped[str | None] = mapped_column(String(50))
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    roles: Mapped[list['Role']] = relationship(
        secondary=f'{SCHEMA}.user_roles',
        back_populates='users', lazy='selectin',
    )
    token_version: Mapped[int] = mapped_column(Integer, default=1, server_default=text('1'))


class Role(Base):
    """Роль — именованный набор разрешений."""

    __tablename__ = 'roles'
    __table_args__ = (
        UniqueConstraint('name', name='uq_roles_name'),
        {'schema': SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    users: Mapped[list[User]] = relationship(
        secondary=f'{SCHEMA}.user_roles', back_populates='roles',
    )
    permissions: Mapped[list['Permission']] = relationship(
        secondary=f'{SCHEMA}.role_permissions',
        back_populates='roles', lazy='selectin',
    )


class Permission(Base):
    """Разрешение (код действия), например film.restricted.view."""

    __tablename__ = 'permissions'
    __table_args__ = (
        UniqueConstraint('codename', name='uq_permissions_codename'),
        {'schema': SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    codename: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    roles: Mapped[list[Role]] = relationship(
        secondary=f'{SCHEMA}.role_permissions', back_populates='permissions',
    )


class UserRole(Base):
    """Связь пользователь–роль."""

    __tablename__ = 'user_roles'
    __table_args__ = {'schema': SCHEMA}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f'{SCHEMA}.users.id', ondelete='CASCADE'),
        primary_key=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f'{SCHEMA}.roles.id', ondelete='CASCADE'),
        primary_key=True,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )


class RolePermission(Base):
    """Связь роль–разрешение."""

    __tablename__ = 'role_permissions'
    __table_args__ = {'schema': SCHEMA}

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f'{SCHEMA}.roles.id', ondelete='CASCADE'),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f'{SCHEMA}.permissions.id', ondelete='CASCADE'),
        primary_key=True,
    )


class LoginHistory(Base):
    """История попыток входа (успешных и нет)."""

    __tablename__ = 'login_history'
    __table_args__ = {'schema': SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f'{SCHEMA}.users.id', ondelete='SET NULL'),
        nullable=True, index=True,
    )
    login: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True,
    )
