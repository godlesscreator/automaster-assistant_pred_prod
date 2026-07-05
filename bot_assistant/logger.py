"""
Модуль логирования.
Централизованная настройка логирования с поддержкой:
- JSON-формат (для отправки в ELK/Grafana)
- Correlation ID (request_id для отслеживания запросов)
- Файл + консоль
- Ротация логов (RotatingFileHandler)
"""

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from bot_assistant.config import get_config


class JSONFormatter(logging.Formatter):
    """
    Форматтер для JSON-логов.
    Используется для централизованного сбора логов (ELK, Grafana, Loki).
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Correlation ID из extra
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id

        # Добавляем traceback если есть
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_entry, ensure_ascii=False)


class CorrelationLogger(logging.Logger):
    """
    Логгер с поддержкой Correlation ID.
    Позволяет передавать request_id через extra.
    """

    def _log_with_request_id(self, level, msg, args, exc_info=None, extra=None, **kwargs):
        if extra is None:
            extra = {}
        super()._log(level, msg, args, exc_info=exc_info, extra=extra, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._log_with_request_id(logging.INFO, msg, args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._log_with_request_id(logging.WARNING, msg, args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._log_with_request_id(logging.ERROR, msg, args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        kwargs["exc_info"] = True
        self._log_with_request_id(logging.ERROR, msg, args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        self._log_with_request_id(logging.DEBUG, msg, args, **kwargs)


# Регистрируем кастомный логгер
logging.setLoggerClass(CorrelationLogger)


def setup_logger(
    name: str = "bot_assistant",
    level: Optional[str] = None,
    log_file: Optional[str] = None,
    use_json: bool = False,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Настраивает и возвращает логгер.

    Args:
        name: Имя логгера
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Путь к файлу лога (если указан, пишет и в файл)
        use_json: Использовать JSON-формат (для ELK/Grafana)
        max_bytes: Максимальный размер файла лога до ротации (по умолч. 10 MB)
        backup_count: Количество хранимых бэкапов при ротации (по умолч. 5)

    Returns:
        Настроенный логгер
    """
    config = get_config()
    log_level = (level or config.logging.level).upper()
    numeric_level = getattr(logging, log_level, logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(numeric_level)

    # Очищаем существующие обработчики
    logger.handlers.clear()

    # Выбираем форматтер
    if use_json:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Файловый обработчик с ротацией
    log_file_path = log_file or config.logging.file
    if log_file_path:
        log_path = Path(log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            encoding="utf-8",
            mode="a",
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "bot_assistant") -> logging.Logger:
    """Возвращает логгер с указанным именем."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger