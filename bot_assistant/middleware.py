"""
Middleware для Flask приложения.
- Correlation ID (request_id для отслеживания запросов)
- Логирование всех HTTP запросов
- Обработка ошибок
- Rate limiting
"""

import time
import uuid
from functools import wraps
from typing import Callable

from flask import Flask, jsonify, request, g

from bot_assistant.errors import BotAssistantError, RateLimitError
from bot_assistant.logger import get_logger

logger = get_logger(__name__)


class CorrelationMiddleware:
    """
    Middleware для добавления Correlation ID к каждому запросу.
    Позволяет связывать логи разных сервисов по request_id.
    """

    def __init__(self, app: Flask):
        self.app = app

    def __call__(self, environ, start_response):
        # Берём ID из заголовка (если пришёл от клиента) или создаём новый
        request_id = (
            environ.get("HTTP_X_REQUEST_ID")
            or environ.get("HTTP_X_CORRELATION_ID")
            or str(uuid.uuid4())
        )
        environ["REQUEST_ID"] = request_id

        def custom_start_response(status, headers, *args):
            # Добавляем request_id в ответ
            headers.append(("X-Request-ID", request_id))
            return start_response(status, headers, *args)

        return self.app(environ, custom_start_response)


class RequestLoggingMiddleware:
    """Middleware для логирования всех HTTP запросов с Correlation ID."""

    def __init__(self, app: Flask):
        self.app = app

    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD", "?")
        path = environ.get("PATH_INFO", "/?")
        request_id = environ.get("REQUEST_ID", "?")
        start = time.time()

        def custom_start_response(status, headers, *args):
            duration = time.time() - start
            logger.info(
                "%s %s -> %s (%.3fs) [request_id=%s]",
                method, path, status, duration, request_id,
            )
            return start_response(status, headers, *args)

        return self.app(environ, custom_start_response)


def register_error_handlers(app: Flask) -> None:
    """Регистрирует обработчики ошибок для Flask приложения."""

    @app.errorhandler(400)
    def bad_request(error):
        logger.warning("400 Bad Request: %s", request.path)
        return jsonify({"error": "Bad request", "message": str(error)}), 400

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        return jsonify({
            "error": "Too many requests",
            "message": "Пожалуйста, подождите перед следующим запросом",
        }), 429

    @app.errorhandler(500)
    def internal_error(error):
        logger.exception("500 Internal Server Error: %s", request.path)
        return jsonify({"error": "Internal server error"}), 500

    @app.errorhandler(BotAssistantError)
    def handle_bot_error(error):
        logger.error("BotAssistantError: %s", error)
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(Exception)
    def handle_unhandled(error):
        logger.exception("Unhandled exception: %s", error)
        # В продакшене не показываем детали ошибки клиенту
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500


class RateLimiter:
    """
    Простой in-memory rate limiter.
    В проде заменить на Redis-based.
    """

    def __init__(self, requests_per_minute: int = 30):
        self.requests_per_minute = requests_per_minute
        self._clients: dict[str, list[float]] = {}

    def is_allowed(self, client_id: str) -> bool:
        """Проверяет, может ли клиент сделать запрос."""
        now = time.time()
        minute_ago = now - 60

        if client_id not in self._clients:
            self._clients[client_id] = []

        # Очищаем старые записи
        self._clients[client_id] = [
            t for t in self._clients[client_id] if t > minute_ago
        ]

        if len(self._clients[client_id]) >= self.requests_per_minute:
            return False

        self._clients[client_id].append(now)
        return True


# Глобальный экземпляр rate limiter
_rate_limiter = RateLimiter()


def rate_limit(f: Callable) -> Callable:
    """Декоратор для rate limiting на эндпоинт."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        client_id = (
            request.headers.get("X-Forwarded-For")
            or request.remote_addr
            or "unknown"
        )
        if not _rate_limiter.is_allowed(client_id):
            raise RateLimitError("Превышен лимит запросов")
        return f(*args, **kwargs)

    return wrapper