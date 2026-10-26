"""Консольные утилиты для управления сервисом аутентификации."""
import asyncio
import re
import sys

import typer
from sqlalchemy import select

from core.security import hash_password
from db.postgres import async_session, engine
from models.auth_models import Role, User

app = typer.Typer(help='Управление сервисом аутентификации')


@app.callback()
def main():
    """Точка входа в консоль управления сервисом."""


def _validate_password(password: str) -> None:
    """Проверяет сложность пароля."""
    errors = []
    if len(password) < 8:
        errors.append('не короче 8 символов')
    if not re.search(r'[A-Z]', password):
        errors.append('хотя бы одна заглавная буква')
    if not re.search(r'[a-z]', password):
        errors.append('хотя бы одна строчная буква')
    if not re.search(r'\d', password):
        errors.append('хотя бы одна цифра')

    if errors:
        typer.secho(
            'Пароль не соответствует требованиям: ' + ', '.join(errors),
            fg='red',
        )
        raise typer.Exit(code=1)


@app.command()
def create_superadmin(
    login: str = typer.Option(..., prompt=True, help='Логин суперпользователя'),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, confirmation_prompt=True, help='Пароль'
    ),
    first_name: str = typer.Option('', prompt=True, help='Имя'),
    last_name: str = typer.Option('', prompt=True, help='Фамилия'),
):
    """Создает пользователя с флагом is_superuser=True и ролью 'admin'."""
    _validate_password(password)

    async def _create() -> tuple[bool, bool]:
        async with async_session() as session:
            stmt = select(User).where(User.login == login)
            result = await session.execute(stmt)
            if result.scalars().first():
                return False, False

            role_result = await session.execute(
                select(Role).where(Role.name == 'admin')
            )
            admin_role = role_result.scalars().first()
            roles_to_assign = [admin_role] if admin_role else []

            user = User(
                login=login,
                hashed_password=hash_password(password),
                first_name=first_name,
                last_name=last_name,
                is_superuser=True,
                roles=roles_to_assign,
            )
            session.add(user)
            await session.commit()

            return True, admin_role is not None

    try:
        created, role_found = asyncio.run(_create())
    except Exception as e:
        typer.secho(f'Ошибка при создании: {e}', fg='red')
        sys.exit(1)
    finally:
        asyncio.run(engine.dispose())

    if not created:
        typer.secho(f'Ошибка: Пользователь {login} уже существует!', fg='red')
        raise typer.Exit(code=1)

    typer.secho(f'Суперпользователь {login} успешно создан!', fg='green')
    if not role_found:
        typer.secho(
            'Роль "admin" не найдена — пользователь создан только с is_superuser',
            fg='yellow',
        )


if __name__ == '__main__':
    app()
