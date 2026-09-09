"""Подключение к БД. База опциональна: без DSN сервис работает без истории запусков."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from mlwrap.config import Settings
from mlwrap.db.models import Base

logger = structlog.get_logger(__name__)


class Database:
    def __init__(self, url: str, *, echo: bool = False, pool_size: int = 5) -> None:
        self.url = url
        kwargs: dict = {"echo": echo, "future": True}
        if not url.startswith("sqlite"):
            kwargs.update(pool_size=pool_size, max_overflow=pool_size, pool_pre_ping=True)
        self.engine: AsyncEngine = create_async_engine(url, **kwargs)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as session:
            yield session

    async def create_all(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def healthcheck(self) -> bool:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("db.healthcheck_failed", error=str(exc))
            return False

    async def dispose(self) -> None:
        await self.engine.dispose()


def build_database(settings: Settings) -> Database | None:
    if not settings.database_url:
        logger.info("db.disabled")
        return None
    return Database(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
    )
