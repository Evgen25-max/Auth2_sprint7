
import asyncio
import os
import sys

import asyncpg


async def wait_for_postgres(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    max_attempts: int = 30,
    sleep_time: float = 2.0,
) -> None:
    """Циклически пытается подключиться к PostgreSQL."""
    print(f"Waiting for PostgreSQL at {host}:{port}...")
    print(f"  User: {user}")
    print(f"  Database: {database}")

    for attempt in range(1, max_attempts + 1):
        try:
            conn = await asyncpg.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                timeout=5.0,
            )
            await conn.close()
            print(f"PostgreSQL is ready! (attempt {attempt})")
            return

        except Exception as e:
            print(f"  Attempt {attempt}/{max_attempts} failed: {type(e).__name__}: {e}")
            if attempt < max_attempts:
                await asyncio.sleep(sleep_time)

    print(f"Failed to connect to PostgreSQL after {max_attempts} attempts")
    sys.exit(1)


def main() -> None:
    host = os.getenv("POSTGRES_HOST", "theatre-db")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    user = os.getenv("POSTGRES_AUTH_USER", "auth_admin")
    password = os.getenv("POSTGRES_AUTH_PASSWORD", "secret")
    # Проверяем системную БД 'postgres' — она есть всегда,
    # даже если целевая БД ещё не создана
    database = os.getenv("POSTGRES_CHECK_DB", "postgres")

    asyncio.run(wait_for_postgres(host, port, user, password, database))


if __name__ == "__main__":
    main()
