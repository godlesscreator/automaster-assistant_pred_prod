"""
Тесты для модуля config.
"""

import os
from unittest.mock import patch

import pytest

from bot_assistant.config import load_config, get_config, reload_config, AppConfig


class TestConfig:
    """Тесты для конфигурации."""

    def test_load_config_defaults(self):
        """Проверка значений по умолчанию."""
        config = load_config()
        assert isinstance(config, AppConfig)
        assert config.tz == "Europe/Moscow"
        assert config.flask.host == "0.0.0.0"
        assert config.flask.port == 8000
        assert config.openai.model == "gpt-4o-mini"
        assert config.telegram.mode == "polling"

    @patch.dict(os.environ, {
        "FLASK_PORT": "9000",
        "OPENAI_MODEL": "gpt-4",
        "TZ": "Asia/Vladivostok",
        "LOG_LEVEL": "DEBUG",
    })
    def test_load_config_from_env(self):
        """Проверка загрузки из переменных окружения."""
        config = load_config()
        assert config.flask.port == 9000
        assert config.openai.model == "gpt-4"
        assert config.tz == "Asia/Vladivostok"
        assert config.logging.level == "DEBUG"

    def test_get_config_singleton(self):
        """Проверка, что get_config возвращает один и тот же экземпляр."""
        c1 = get_config()
        c2 = get_config()
        assert c1 is c2

    def test_reload_config(self):
        """Проверка перезагрузки конфигурации."""
        c1 = get_config()
        c2 = reload_config()
        assert c1 is not c2


class TestFlaskConfig:
    """Тесты для Flask конфигурации."""

    @patch.dict(os.environ, {
        "FLASK_HOST": "127.0.0.1",
        "FLASK_PORT": "5000",
        "FLASK_DEBUG": "true",
        "FLASK_SECRET_KEY": "super-secret",
    })
    def test_flask_config(self):
        config = load_config()
        assert config.flask.host == "127.0.0.1"
        assert config.flask.port == 5000
        assert config.flask.debug is True
        assert config.flask.secret_key == "super-secret"


class TestTelegramConfig:
    """Тесты для Telegram конфигурации."""

    @patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "123:abc",
        "TELEGRAM_ADMIN_CHAT_ID": "-100123456789",
        "TELEGRAM_MODE": "webhook",
    })
    def test_telegram_config(self):
        config = load_config()
        assert config.telegram.bot_token == "123:abc"
        assert config.telegram.admin_chat_id == "-100123456789"
        assert config.telegram.mode == "webhook"


class TestDatabaseConfig:
    """Тесты для Database конфигурации."""

    @patch.dict(os.environ, {
        "DATABASE_ENABLED": "true",
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/testdb",
        "DATABASE_POOL_SIZE": "10",
    })
    def test_database_config(self):
        config = load_config()
        assert config.database.enabled is True
        assert config.database.url == "postgresql://user:pass@localhost:5432/testdb"
        assert config.database.pool_size == 10
        assert config.database.max_overflow == 10  # default

    def test_database_disabled_by_default(self):
        config = load_config()
        assert config.database.enabled is False


class TestSentryConfig:
    """Тесты для Sentry конфигурации."""

    @patch.dict(os.environ, {
        "SENTRY_ENABLED": "true",
        "SENTRY_DSN": "https://key@sentry.io/123",
        "SENTRY_TRACES_SAMPLE_RATE": "0.5",
    })
    def test_sentry_config(self):
        config = load_config()
        assert config.sentry.enabled is True
        assert config.sentry.dsn == "https://key@sentry.io/123"
        assert config.sentry.traces_sample_rate == 0.5

    def test_sentry_disabled_by_default(self):
        config = load_config()
        assert config.sentry.enabled is False


class TestLoggingConfig:
    """Тесты для Logging конфигурации."""

    @patch.dict(os.environ, {
        "LOG_JSON": "true",
        "LOG_LEVEL": "DEBUG",
        "LOG_FILE": "logs/test.log",
    })
    def test_logging_config(self):
        config = load_config()
        assert config.logging.use_json is True
        assert config.logging.level == "DEBUG"
        assert config.logging.file == "logs/test.log"

    def test_logging_defaults(self):
        config = load_config()
        assert config.logging.use_json is False