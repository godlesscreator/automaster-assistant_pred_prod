"""
Тесты для middleware.
"""

import time
import uuid
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from bot_assistant.middleware import (
    CorrelationMiddleware,
    RequestLoggingMiddleware,
    RateLimiter,
    register_error_handlers,
)


class TestCorrelationMiddleware:
    """Тесты для CorrelationMiddleware."""

    def test_adds_request_id_from_header(self):
        """Проверка, что request_id берётся из заголовка X-Request-ID."""
        app = Flask(__name__)
        app.wsgi_app = CorrelationMiddleware(app.wsgi_app)

        @app.route("/test")
        def test():
            from flask import request
            from bot_assistant.logger import get_logger
            logger = get_logger(__name__)
            logger.info("Test request", extra={"request_id": request.environ.get("REQUEST_ID", "?")})
            return {"request_id": request.environ.get("REQUEST_ID", "?")}

        client = app.test_client()
        test_id = "test-request-123"
        response = client.get("/test", headers={"X-Request-ID": test_id})
        assert response.status_code == 200
        data = response.get_json()
        assert data["request_id"] == test_id

    def test_generates_request_id_if_missing(self):
        """Проверка, что request_id генерируется, если заголовка нет."""
        app = Flask(__name__)
        app.wsgi_app = CorrelationMiddleware(app.wsgi_app)

        @app.route("/test")
        def test():
            from flask import request
            return {"request_id": request.environ.get("REQUEST_ID", "?")}

        client = app.test_client()
        response = client.get("/test")
        assert response.status_code == 200
        data = response.get_json()
        # Должен быть сгенерирован UUID
        assert data["request_id"] != "?"
        assert len(data["request_id"]) > 10

    def test_returns_request_id_in_response_header(self):
        """Проверка, что X-Request-ID добавляется в заголовки ответа."""
        app = Flask(__name__)
        app.wsgi_app = CorrelationMiddleware(app.wsgi_app)

        @app.route("/test")
        def test():
            return {"status": "ok"}

        client = app.test_client()
        response = client.get("/test")
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 10

    def test_uses_x_correlation_id_header(self):
        """Проверка, что X-Correlation-ID также поддерживается."""
        app = Flask(__name__)
        app.wsgi_app = CorrelationMiddleware(app.wsgi_app)

        @app.route("/test")
        def test():
            from flask import request
            return {"request_id": request.environ.get("REQUEST_ID", "?")}

        client = app.test_client()
        test_id = "correlation-456"
        response = client.get("/test", headers={"X-Correlation-ID": test_id})
        data = response.get_json()
        assert data["request_id"] == test_id


class TestRequestLoggingMiddleware:
    """Тесты для RequestLoggingMiddleware."""

    def test_logs_request(self, caplog):
        """Проверка, что запрос логируется."""
        import logging
        caplog.set_level(logging.INFO)

        app = Flask(__name__)
        app.wsgi_app = CorrelationMiddleware(app.wsgi_app)
        app.wsgi_app = RequestLoggingMiddleware(app.wsgi_app)

        @app.route("/test")
        def test():
            return {"status": "ok"}

        client = app.test_client()
        response = client.get("/test")
        assert response.status_code == 200

        # Проверяем, что в логах есть запись о запросе
        found = False
        for record in caplog.records:
            if "GET" in record.getMessage() and "/test" in record.getMessage():
                found = True
                break
        assert found, "Request log entry not found"


class TestRateLimiter:
    """Тесты для RateLimiter."""

    def test_is_allowed_first_request(self):
        """Проверка, что первый запрос разрешён."""
        limiter = RateLimiter(requests_per_minute=10)
        assert limiter.is_allowed("client1") is True

    def test_is_allowed_within_limit(self):
        """Проверка, что запросы в пределах лимита разрешены."""
        limiter = RateLimiter(requests_per_minute=5)
        for _ in range(5):
            assert limiter.is_allowed("client2") is True

    def test_is_blocked_when_exceeds_limit(self):
        """Проверка, что при превышении лимита запрос блокируется."""
        limiter = RateLimiter(requests_per_minute=3)
        for _ in range(3):
            assert limiter.is_allowed("client3") is True
        # 4-й запрос должен быть заблокирован
        assert limiter.is_allowed("client3") is False

    def test_different_clients_have_separate_limits(self):
        """Проверка, что лимиты для разных клиентов независимы."""
        limiter = RateLimiter(requests_per_minute=2)
        assert limiter.is_allowed("client_a") is True
        assert limiter.is_allowed("client_a") is True
        assert limiter.is_allowed("client_a") is False  # Лимит исчерпан

        # Другой клиент не затронут
        assert limiter.is_allowed("client_b") is True
        assert limiter.is_allowed("client_b") is True

    def test_old_entries_are_cleaned(self):
        """Проверка, что старые записи очищаются."""
        limiter = RateLimiter(requests_per_minute=2)

        # Добавляем старую запись вручную
        old_time = time.time() - 120  # 2 минуты назад
        limiter._clients["client_old"] = [old_time]

        # Новый запрос должен быть разрешён (старая запись очищена)
        assert limiter.is_allowed("client_old") is True


class TestErrorHandlers:
    """Тесты для обработчиков ошибок."""

    @pytest.fixture
    def app(self):
        app = Flask(__name__)
        register_error_handlers(app)

        @app.route("/error-400")
        def error_400():
            from flask import abort
            abort(400)

        @app.route("/error-404")
        def error_404():
            from flask import abort
            abort(404)

        @app.route("/error-500")
        def error_500():
            raise RuntimeError("Test internal error")

        return app

    def test_400_handler(self, app):
        client = app.test_client()
        response = client.get("/error-400")
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_404_handler(self, app):
        client = app.test_client()
        response = client.get("/nonexistent")
        assert response.status_code == 404
        data = response.get_json()
        assert data["error"] == "Not found"

    def test_500_handler(self, app):
        client = app.test_client()
        response = client.get("/error-500")
        assert response.status_code == 500
        data = response.get_json()
        assert "error" in data