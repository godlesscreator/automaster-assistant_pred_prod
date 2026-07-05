"""
Модуль для работы с PostgreSQL через SQLAlchemy.
Обеспечивает подключение к БД и управление сессиями.
"""

import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from bot_assistant.config import AppConfig

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Базовый класс для всех SQLAlchemy моделей."""
    pass


class DatabaseManager:
    """
    Менеджер подключения к БД.

    Управляет engine и sessionmaker. Не использует глобальные переменные.
    Создаётся через DI контейнер.

    Usage:
        db_manager = DatabaseManager(config)
        with db_manager.get_db() as db:
            if db:
                db.query(...)
    """

    def __init__(self, config: AppConfig):
        self._config = config
        self._engine = None
        self._SessionLocal = None

    def _get_engine(self):
        """Возвращает engine (с ленивой инициализацией)."""
        if self._engine is None:
            if not self._config.database.enabled:
                logger.info("Database is disabled, skipping engine creation")
                return None
            self._engine = create_engine(
                self._config.database.url,
                pool_size=self._config.database.pool_size,
                max_overflow=self._config.database.max_overflow,
                pool_pre_ping=True,
                echo=self._config.database.echo,
            )
            logger.info("Database engine created: %s", self._config.database.url)
        return self._engine

    def _get_session_local(self):
        """Возвращает sessionmaker (с ленивой инициализацией)."""
        if self._SessionLocal is None:
            engine = self._get_engine()
            if engine is None:
                return None
            self._SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        return self._SessionLocal

    @contextmanager
    def get_db(self) -> Generator[Optional[Session], None, None]:
        """
        Контекстный менеджер для получения сессии БД.
        Автоматически закрывает сессию после использования.
        """
        session_local = self._get_session_local()
        if session_local is None:
            yield None
            return

        db = session_local()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def init_db(self):
        """Создаёт все таблицы в БД (если их нет)."""
        engine = self._get_engine()
        if engine is None:
            logger.info("Database disabled, skipping table creation")
            return
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")

    def close(self):
        """Закрывает соединение с БД."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
            self._SessionLocal = None
            logger.info("Database connection closed")


# Для обратной совместимости — функции-прокси, использующие DI контейнер
def get_db() -> Generator[Optional[Session], None, None]:
    """Прокси для обратной совместимости. Использует DI контейнер."""
    from bot_assistant.di import get_container
    container = get_container()
    if container.database:
        with container.database.get_db() as db:
            yield db
    else:
        yield None


def init_db():
    """Прокси для обратной совместимости."""
    from bot_assistant.di import get_container
    container = get_container()
    if container.database:
        container.database.init_db()


def close_db():
    """Прокси для обратной совместимости."""
    from bot_assistant.di import get_container
    container = get_container()
    if container.database:
        container.database.close()