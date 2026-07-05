"""
Dependency Injection контейнер.
Централизованное управление зависимостями приложения.

Заменяет глобальные синглтоны (_config, _engine, _redis_client, _repository)
на явное внедрение зависимостей через контейнер.
"""

import logging
from typing import Optional

import sentry_sdk

from bot_assistant.config import AppConfig, load_config
from bot_assistant.database import DatabaseManager
from bot_assistant.logger import setup_logger
from bot_assistant.redis_client import RedisClient
from bot_assistant.repository import (
    LeadRepository,
    PostgresLeadRepository,
    GoogleSheetsLeadRepository,
    create_lead_repository,
)
from bot_assistant.services.google_sheets import GoogleSheetsService
from bot_assistant.services.openai_service import OpenAIService
from bot_assistant.services.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)


class Container:
    """
    DI контейнер приложения.

    Управляет жизненным циклом всех зависимостей:
    - Config (AppConfig)
    - Database (DatabaseManager)
    - Redis (RedisClient)
    - Repository (LeadRepository)
    - Services (OpenAI, Google Sheets, Telegram)

    Использование:
        container = Container()
        container.initialize()
        repo = container.get_lead_repository()
    """

    def __init__(self):
        self._config: Optional[AppConfig] = None
        self._database: Optional["DatabaseManager"] = None
        self._redis: Optional[RedisClient] = None
        self._repository: Optional[LeadRepository] = None
        self._openai_service: Optional[OpenAIService] = None
        self._sheets_service: Optional[GoogleSheetsService] = None
        self._notifier: Optional[TelegramNotifier] = None
        self._initialized = False

    def initialize(self) -> None:
        """Инициализирует все зависимости."""
        if self._initialized:
            return

        # Config — всегда первым
        self._config = load_config()

        # Настройка логирования
        setup_logger(
            level=self._config.logging.level,
            log_file=self._config.logging.file or None,
            use_json=self._config.logging.use_json,
        )

        # Sentry (только если включён и настроен DSN)
        if self._config.sentry.enabled and self._config.sentry.dsn:
            sentry_sdk.init(
                dsn=self._config.sentry.dsn,
                traces_sample_rate=self._config.sentry.traces_sample_rate,
                environment="production",
                release="automaster-assistant@1.0.0",
                send_default_pii=False,
            )
            logger.info(
                "Sentry initialized (DSN: ...%s, sample_rate: %.2f)",
                self._config.sentry.dsn[-8:],
                self._config.sentry.traces_sample_rate,
            )

        # Database (лениво, только если включена)
        if self._config.database.enabled:
            self._database = DatabaseManager(self._config)

        # Redis (лениво, только если включён)
        if self._config.redis.enabled:
            self._redis = RedisClient()

        # Repository
        self._repository = create_lead_repository(self._config, self._database)

        # Services
        self._openai_service = OpenAIService(self._config)
        self._sheets_service = GoogleSheetsService(self._config)
        self._notifier = TelegramNotifier(self._config)

        self._initialized = True
        logger.info("DI Container initialized successfully")

    def shutdown(self) -> None:
        """Graceful shutdown всех зависимостей."""
        if self._database:
            self._database.close()
        if self._redis:
            self._redis.close()
        self._initialized = False
        logger.info("DI Container shut down")

    # ---- Config ----

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            self._config = load_config()
        return self._config

    # ---- Database ----

    @property
    def database(self) -> Optional["DatabaseManager"]:
        if self._database is None and self.config.database.enabled:
            self._database = DatabaseManager(self.config)
        return self._database

    # ---- Redis ----

    @property
    def redis(self) -> Optional[RedisClient]:
        if self._redis is None and self.config.redis.enabled:
            self._redis = RedisClient()
        return self._redis

    # ---- Repository ----

    def get_lead_repository(self) -> LeadRepository:
        if self._repository is None:
            self._repository = create_lead_repository(self.config, self.database)
        return self._repository

    def reset_repository(self) -> None:
        """Сбрасывает репозиторий (для тестов)."""
        self._repository = None

    # ---- Services ----

    def get_openai_service(self) -> OpenAIService:
        if self._openai_service is None:
            self._openai_service = OpenAIService(self.config)
        return self._openai_service

    def get_sheets_service(self) -> GoogleSheetsService:
        if self._sheets_service is None:
            self._sheets_service = GoogleSheetsService(self.config)
        return self._sheets_service

    def get_notifier(self) -> TelegramNotifier:
        if self._notifier is None:
            self._notifier = TelegramNotifier(self.config)
        return self._notifier


# Глобальный экземпляр контейнера (единственный синглтон, который остаётся)
_container: Optional[Container] = None


def get_container() -> Container:
    """Возвращает глобальный экземпляр DI контейнера."""
    global _container
    if _container is None:
        _container = Container()
    return _container


def reset_container() -> None:
    """Сбрасывает контейнер (для тестов)."""
    global _container
    if _container:
        _container.shutdown()
    _container = None