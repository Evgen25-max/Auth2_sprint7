
import logging

from api.const import (PERM_FILM_RESTRICTED_VIEW, PERM_ROLE_MANAGE,
                       PERM_USER_MANAGE)
from models.auth_models import Permission, Role
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

# Системные права: (codename, описание)
SYSTEM_PERMISSIONS = [
    (PERM_USER_MANAGE, 'Управление пользователями'),
    (PERM_ROLE_MANAGE, 'Управление ролями и правами'),
    (PERM_FILM_RESTRICTED_VIEW, 'Просмотр фильмов с ограниченным доступом'),
]

# Системные роли: (name, description, список codename прав)
SYSTEM_ROLES = [
    ('user', 'Базовый пользователь', []),
    (
        'admin',
        'Администратор сервиса',
        [
            PERM_USER_MANAGE,
            PERM_ROLE_MANAGE,
            PERM_FILM_RESTRICTED_VIEW,
        ],
    ),
]


async def seed_default_permissions(session: AsyncSession) -> dict[str, Permission]:
    """Создаёт системные права, если их нет.
    Возвращает словарь codename -> Permission.
    """
    perms_by_code: dict[str, Permission] = {}

    for codename, name in SYSTEM_PERMISSIONS:
        result = await session.execute(
            select(Permission).where(Permission.codename == codename)
        )
        perm = result.scalars().first()

        if perm is None:
            perm = Permission(codename=codename, name=name)
            session.add(perm)
            await session.flush()
            logger.info('Создано право: %s', codename)
        else:
            logger.debug('Право %s уже существует', codename)

        perms_by_code[codename] = perm

    return perms_by_code


async def seed_default_roles(
    session: AsyncSession,
    perms_by_code: dict[str, Permission],
) -> None:
    """Создаёт системные роли и назначает им права."""
    for role_name, role_description, perm_codenames in SYSTEM_ROLES:
        desired_perms = [
            perms_by_code[codename]
            for codename in perm_codenames
            if codename in perms_by_code
        ]

        result = await session.execute(
            select(Role)
            .options(selectinload(Role.permissions))
            .where(Role.name == role_name)
        )
        role = result.scalars().first()

        if role is None:
            role = Role(
                name=role_name,
                description=role_description,
                permissions=desired_perms,
            )
            session.add(role)
            await session.flush()
            logger.info('Создана роль: %s', role_name)

            continue

        logger.debug('Роль %s уже существует', role_name)

        current_perm_ids = {perm.id for perm in role.permissions}

        for perm in desired_perms:
            if perm.id not in current_perm_ids:
                role.permissions.append(perm)
                logger.info(
                    'Роли %s назначено право %s',
                    role_name,
                    perm.codename,
                )

    await session.commit()


async def seed_system_data(session: AsyncSession) -> None:
    """Главная точка входа: сидирует права и роли."""
    logger.info('Запуск сидирования системных данных...')

    try:
        perms = await seed_default_permissions(session)
        await seed_default_roles(session, perms)
        logger.info('Сидирование завершено успешно')
    except Exception:
        await session.rollback()
        logger.exception('Ошибка при сидировании системных данных')
        raise
