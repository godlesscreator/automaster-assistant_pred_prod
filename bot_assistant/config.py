"""
Модуль конфигурации приложения.
Централизованное управление настройками из .env файла.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv


class ConfigValidationError(Exception):
    """Ошибка валидации конфигурации."""
    pass


@dataclass
class FlaskConfig:
    """Настройки Flask сервера."""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    web_origin: str = "http://localhost:8000"
    secret_key: str = ""  # Должен быть установлен через .env!
    session_lifetime_days: int = 7


@dataclass
class TelegramConfig:
    """Настройки Telegram бота."""
    bot_token: str = ""
    admin_chat_id: str = ""
    mode: str = "polling"  # polling | webhook
    webhook_url: str = ""
    webhook_secret: str = ""


@dataclass
class OpenAIConfig:
    """Настройки OpenAI."""
    api_key: str = ""
    model: str = "gpt-4o-mini"
    assistant_id: str = ""
    temperature: float = 0.3
    max_tokens: int = 1024


@dataclass
class GoogleSheetsConfig:
    """Настройки Google Sheets."""
    sheets_id: str = ""
    api_key: str = ""
    credentials_file: str = "credentials.json"
    sheets_range: str = "'админ'!A1"
    sheets_columns: str = "name,phone,car,service,desired_datetime,comment"


@dataclass
class DatabaseConfig:
    """Настройки PostgreSQL (опционально)."""
    enabled: bool = False
    url: str = "postgresql://postgres:postgres@localhost:5432/automaster"
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False


@dataclass
class RedisConfig:
    """Настройки Redis (опционально)."""
    enabled: bool = False
    url: str = "redis://localhost:6379/0"


@dataclass
class AdminConfig:
    """Настройки админ-панели."""
    username: str = "admin"
    password: str = ""  # Должен быть установлен через .env!
    enabled: bool = True


@dataclass
class SentryConfig:
    """Настройки Sentry (опционально)."""
    enabled: bool = False
    dsn: str = ""
    traces_sample_rate: float = 0.1


@dataclass
class LoggingConfig:
    """Настройки логирования."""
    level: str = "INFO"
    file: str = ""
    use_json: bool = False


@dataclass
class AppConfig:
    """Главная конфигурация приложения."""
    tz: str = "Europe/Moscow"
    tilda_site_url: str = ""
    ngrok_authtoken: str = ""

    flask: FlaskConfig = field(default_factory=FlaskConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    google_sheets: GoogleSheetsConfig = field(default_factory=GoogleSheetsConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    admin: AdminConfig = field(default_factory=AdminConfig)
    sentry: SentryConfig = field(default_factory=SentryConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def validate(self, strict: bool = False) -> list[str]:
        """
        Проверяет конфигурацию на проблемы.

        Args:
            strict: Если True — выбрасывает ConfigValidationError вместо возврата списка

        Returns:
            Список предупреждений (если strict=False)

        Raises:
            ConfigValidationError: если strict=True и есть критические проблемы
        """
        warnings = []
        errors = []

        # Проверка secret_key — теперь критично
        if not self.flask.secret_key:
            msg = (
                "FLASK_SECRET_KEY не установлен! Это критично для безопасности. "
                "Установите FLASK_SECRET_KEY в .env файле."
            )
            errors.append(msg)
            warnings.append(msg)
        elif self.flask.secret_key == "change-me-in-production":
            msg = (
                "FLASK_SECRET_KEY использует значение по умолчанию! "
                "Установите свой уникальный секретный ключ в .env файле."
            )
            warnings.append(msg)

        # Проверка admin пароля — теперь критично
        if self.admin.enabled and not self.admin.password:
            msg = (
                "ADMIN_PASSWORD не установлен! Админ-панель будет доступна без пароля. "
                "Установите ADMIN_PASSWORD в .env файле."
            )
            errors.append(msg)
            warnings.append(msg)

        # Проверка обязательных полей
        if not self.telegram.bot_token:
            warnings.append("TELEGRAM_BOT_TOKEN не настроен — Telegram бот отключён")

        if not self.openai.api_key:
            warnings.append("OPENAI_API_KEY не настроен — AI консультации отключены")

        if not self.google_sheets.sheets_id:
            warnings.append("GOOGLE_SHEETS_ID не настроен — заявки не будут сохраняться")

        # Проверка режима webhook
        if self.telegram.mode == "webhook" and not self.telegram.webhook_url:
            warnings.append(
                "TELEGRAM_MODE=webhook, но TELEGRAM_WEBHOOK_URL не указан. "
                "Бот будет работать в режиме polling."
            )

        if strict and errors:
            raise ConfigValidationError(
                "Критические ошибки конфигурации:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        return warnings


def load_config() -> AppConfig:
    """
    Загружает конфигурацию из переменных окружения.
    Вызывается один раз при старте приложения.
    """
    load_dotenv()

    config = AppConfig(
        tz=os.getenv("TZ", "Europe/Moscow"),
        tilda_site_url=os.getenv("TILDA_SITE_URL", ""),
        ngrok_authtoken=os.getenv("NGROK_AUTHTOKEN", ""),
        flask=FlaskConfig(
            host=os.getenv("FLASK_HOST", "0.0.0.0"),
            port=int(os.getenv("FLASK_PORT", "8000")),
            debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
            web_origin=os.getenv("WEB_ORIGIN", "http://localhost:8000"),
            secret_key=os.getenv("FLASK_SECRET_KEY", ""),
            session_lifetime_days=int(os.getenv("SESSION_LIFETIME_DAYS", "7")),
        ),
        telegram=TelegramConfig(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            admin_chat_id=os.getenv("TELEGRAM_ADMIN_CHAT_ID", ""),
            mode=os.getenv("TELEGRAM_MODE", "polling"),
            webhook_url=os.getenv("TELEGRAM_WEBHOOK_URL", ""),
            webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET", ""),
        ),
        openai=OpenAIConfig(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            assistant_id=os.getenv("OPENAI_ASSISTANT_ID", ""),
            temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.3")),
            max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "1024")),
        ),
        google_sheets=GoogleSheetsConfig(
            sheets_id=os.getenv("GOOGLE_SHEETS_ID", ""),
            api_key=os.getenv("GOOGLE_API_KEY", ""),
            credentials_file=os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"),
            sheets_range=os.getenv("GOOGLE_SHEETS_RANGE", "'админ'!A1"),
            sheets_columns=os.getenv("GOOGLE_SHEETS_COLUMNS", "name,phone,car,service,desired_datetime,comment"),
        ),
        database=DatabaseConfig(
            enabled=os.getenv("DATABASE_ENABLED", "false").lower() == "true",
            url=os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/automaster"),
            pool_size=int(os.getenv("DATABASE_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "10")),
            echo=os.getenv("DATABASE_ECHO", "false").lower() == "true",
        ),
        redis=RedisConfig(
            enabled=os.getenv("REDIS_ENABLED", "false").lower() == "true",
            url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        ),
        admin=AdminConfig(
            username=os.getenv("ADMIN_USERNAME", "admin"),
            password=os.getenv("ADMIN_PASSWORD", ""),
            enabled=os.getenv("ADMIN_ENABLED", "true").lower() == "true",
        ),
        sentry=SentryConfig(
            enabled=os.getenv("SENTRY_ENABLED", "false").lower() == "true",
            dsn=os.getenv("SENTRY_DSN", ""),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        ),
        logging=LoggingConfig(
            level=os.getenv("LOG_LEVEL", "INFO"),
            file=os.getenv("LOG_FILE", ""),
            use_json=os.getenv("LOG_JSON", "false").lower() == "true",
        ),
    )
    return config


# Глобальный экземпляр конфигурации (ленивая инициализация)
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Возвращает глобальный экземпляр конфигурации."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> AppConfig:
    """Принудительная перезагрузка конфигурации."""
    global _config
    _config = load_config()
    return _config