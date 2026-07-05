"""
Тесты для Flask эндпоинтов.
"""

from unittest.mock import patch, MagicMock

import pytest

from bot_assistant.models import Lead


@pytest.fixture
def app():
    """Создаёт Flask приложение для тестов."""
    import os
    from flask import Flask
    from bot_assistant.handlers import (
        get_webchat_bp, get_admin_bp, get_api_v1_bp, get_docs_bp,
    )
    from bot_assistant.handlers.web_chat import WEB_SESSIONS

    # Очищаем сессии между тестами
    WEB_SESSIONS.clear()

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret-key-for-testing"
    # Указываем путь к папке с шаблонами
    templates_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "bot_assistant", "templates"
    )
    app.config["TEMPLATE_FOLDER"] = templates_path
    app.jinja_loader.searchpath = [templates_path]
    app.register_blueprint(get_webchat_bp())
    app.register_blueprint(get_admin_bp())
    app.register_blueprint(get_api_v1_bp())
    app.register_blueprint(get_docs_bp())

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "2.0.0"}

    @app.get("/")
    def root():
        return {"service": "test"}

    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestWebChat:
    """Тесты для веб-чата."""

    def test_webchat_missing_message(self, client):
        """Проверка запроса без сообщения."""
        response = client.post("/webchat", json={})
        assert response.status_code == 200
        data = response.get_json()
        assert "reply" in data
        assert data["lead_saved"] is False

    def test_webchat_with_message(self, client):
        """Проверка запроса с сообщением (с CSRF-токеном)."""
        # Первый запрос — начало диалога, CSRF не требуется
        first_response = client.post("/webchat", json={
            "message": "Привет",
            "name": "Иван",
        })
        assert first_response.status_code == 200
        first_data = first_response.get_json()
        csrf_token = first_data.get("csrf_token", "")

        # Второй запрос — требуется CSRF-токен
        response = client.post("/webchat", json={
            "message": "+79991234567",
            "phone": "+79991234567",
            "csrf_token": csrf_token,
        })
        assert response.status_code == 200
        data = response.get_json()
        assert "reply" in data

    def test_webchat_csrf_required_for_existing_session(self, client):
        """Проверка, что CSRF требуется для существующей сессии."""
        # Начинаем диалог
        first = client.post("/webchat", json={"message": "Привет", "name": "Иван"})
        assert first.status_code == 200

        # Отправляем запрос без CSRF-токена — должно быть 403
        response = client.post("/webchat", json={
            "message": "+79991234567",
            "phone": "+79991234567",
        })
        assert response.status_code == 403
        data = response.get_json()
        assert "csrf_token" not in data  # Нет токена в ответе на ошибку

    def test_webchat_invalid_json(self, client):
        """Проверка невалидного JSON."""
        response = client.post(
            "/webchat",
            data="not json",
            content_type="application/json",
        )
        assert response.status_code == 400


class TestHealth:
    """Тесты для health endpoints."""

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["version"] == "2.0.0"

    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.get_json()
        assert "service" in data


class TestAdmin:
    """Тесты для админ-панели."""

    @patch("bot_assistant.handlers.admin_panel.get_config")
    @patch("bot_assistant.services.get_lead_repository")
    def test_admin_dashboard_no_auth(self, mock_get_repo, mock_config, client):
        """Проверка, что без пароля админка доступна."""
        mock_cfg = MagicMock()
        mock_cfg.admin.enabled = True
        mock_cfg.admin.password = ""  # Пароль не установлен
        mock_cfg.admin.username = "admin"
        mock_config.return_value = mock_cfg

        mock_repo = MagicMock()
        mock_repo.get_all.return_value = []
        mock_get_repo.return_value = mock_repo

        response = client.get("/admin/")
        assert response.status_code == 200

    @patch("bot_assistant.handlers.admin_panel.get_config")
    def test_admin_dashboard_requires_auth(self, mock_config, client):
        """Проверка, что с паролем требуется аутентификация."""
        mock_cfg = MagicMock()
        mock_cfg.admin.enabled = True
        mock_cfg.admin.password = "secret123"
        mock_cfg.admin.username = "admin"
        mock_config.return_value = mock_cfg

        response = client.get("/admin/")
        assert response.status_code == 401  # Unauthorized

    @patch("bot_assistant.handlers.admin_panel.get_config")
    @patch("bot_assistant.services.get_lead_repository")
    def test_admin_dashboard_with_auth(self, mock_get_repo, mock_config, client):
        """Проверка доступа с правильными credentials."""
        mock_cfg = MagicMock()
        mock_cfg.admin.enabled = True
        mock_cfg.admin.password = "secret123"
        mock_cfg.admin.username = "admin"
        mock_config.return_value = mock_cfg

        mock_repo = MagicMock()
        mock_repo.get_all.return_value = []
        mock_get_repo.return_value = mock_repo

        from base64 import b64encode
        credentials = b64encode(b"admin:secret123").decode("utf-8")
        response = client.get(
            "/admin/",
            headers={"Authorization": f"Basic {credentials}"},
        )
        assert response.status_code == 200

    @patch("bot_assistant.handlers.admin_panel.get_config")
    @patch("bot_assistant.services.get_lead_repository")
    def test_admin_leads(self, mock_get_repo, mock_config, client):
        """Проверка получения заявок."""
        mock_cfg = MagicMock()
        mock_cfg.admin.enabled = True
        mock_cfg.admin.password = ""
        mock_cfg.admin.username = "admin"
        mock_config.return_value = mock_cfg

        mock_repo = MagicMock()
        mock_repo.get_all.return_value = []
        mock_get_repo.return_value = mock_repo

        response = client.get("/admin/leads")
        assert response.status_code == 200
        data = response.get_json()
        assert data == []


class TestAPIV1:
    """Тесты для API v1."""

    @patch("bot_assistant.handlers.api_v1.get_lead_repository")
    def test_create_lead_success(self, mock_get_repo, client):
        """Проверка успешного создания заявки через API v1."""
        mock_repo = MagicMock()
        mock_repo.add.return_value = Lead(
            name="Иван",
            phone="+79991234567",
            car="Toyota",
            service="Ремонт",
            desired_datetime="2026-12-25 14:00",
        )
        mock_get_repo.return_value = mock_repo

        response = client.post("/api/v1/leads", json={
            "name": "Иван",
            "phone": "+79991234567",
            "car": "Toyota",
            "service": "Ремонт",
            "desired_datetime": "2026-12-25 14:00",
        })
        assert response.status_code == 201
        data = response.get_json()
        assert data["status"] == "created"
        assert data["lead"]["name"] == "Иван"

    def test_create_lead_missing_fields(self, client):
        """Проверка ошибки при отсутствии обязательных полей."""
        response = client.post("/api/v1/leads", json={
            "name": "Иван",
        })
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_create_lead_invalid_json(self, client):
        """Проверка невалидного JSON."""
        response = client.post(
            "/api/v1/leads",
            data="not json",
            content_type="application/json",
        )
        assert response.status_code == 400

    @patch("bot_assistant.handlers.api_v1.get_lead_repository")
    def test_list_leads(self, mock_get_repo, client):
        """Проверка получения списка заявок."""
        mock_repo = MagicMock()
        mock_repo.get_all.return_value = [
            Lead(name="Иван", phone="+79991234567"),
            Lead(name="Петр", phone="+79991112233"),
        ]
        mock_repo.count.return_value = 2
        mock_get_repo.return_value = mock_repo

        response = client.get("/api/v1/leads")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["leads"]) == 2
        assert data["total"] == 2

    @patch("bot_assistant.handlers.api_v1.get_lead_repository")
    def test_get_lead_by_id(self, mock_get_repo, client):
        """Проверка получения заявки по ID."""
        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = Lead(
            name="Иван",
            phone="+79991234567",
            car="Toyota",
        )
        mock_get_repo.return_value = mock_repo

        response = client.get("/api/v1/leads/1")
        assert response.status_code == 200
        data = response.get_json()
        assert data["lead"]["name"] == "Иван"

    @patch("bot_assistant.handlers.api_v1.get_lead_repository")
    def test_get_lead_not_found(self, mock_get_repo, client):
        """Проверка 404 при отсутствии заявки."""
        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = None
        mock_get_repo.return_value = mock_repo

        response = client.get("/api/v1/leads/999")
        assert response.status_code == 404

    @patch("bot_assistant.handlers.api_v1.get_lead_repository")
    def test_update_lead_status(self, mock_get_repo, client):
        """Проверка обновления статуса заявки."""
        mock_repo = MagicMock()
        mock_repo.update_status.return_value = True
        mock_get_repo.return_value = mock_repo

        response = client.patch("/api/v1/leads/1/status", json={
            "status": "contacted",
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data["new_status"] == "contacted"

    @patch("bot_assistant.handlers.api_v1.get_lead_repository")
    def test_update_lead_status_invalid(self, mock_get_repo, client):
        """Проверка ошибки при невалидном статусе."""
        response = client.patch("/api/v1/leads/1/status", json={
            "status": "invalid_status",
        })
        assert response.status_code == 400

    @patch("bot_assistant.handlers.api_v1.get_lead_repository")
    def test_api_v1_health(self, mock_get_repo, client):
        """Проверка health endpoint API v1."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["api_version"] == "v1"
        assert data["status"] == "ok"


class TestDocs:
    """Тесты для документации API."""

    def test_openapi_spec_returns_yaml(self, client):
        """Проверка, что /openapi.yaml возвращает YAML файл."""
        response = client.get("/openapi.yaml")
        assert response.status_code == 200
        assert "text/yaml" in response.content_type
        assert b"openapi:" in response.data
        assert b"AutoMaster+ Assistant API" in response.data

    def test_openapi_spec_contains_paths(self, client):
        """Проверка, что спецификация содержит все эндпоинты."""
        response = client.get("/openapi.yaml")
        content = response.data.decode("utf-8")
        assert "/health" in content
        assert "/api/v1/leads" in content
        assert "/webchat" in content
        assert "/admin/" in content

    def test_swagger_ui_returns_html(self, client):
        """Проверка, что /docs возвращает HTML страницу Swagger UI."""
        response = client.get("/docs")
        assert response.status_code == 200
        assert response.content_type.startswith("text/html")
        assert b"swagger-ui" in response.data
        assert b"openapi.yaml" in response.data