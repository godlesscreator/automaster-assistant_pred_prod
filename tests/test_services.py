"""
Тесты для сервисов (с моками).
"""

from unittest.mock import patch, MagicMock

import pytest
import requests
import responses

from bot_assistant.services.google_sheets import GoogleSheetsService
from bot_assistant.services.openai_service import OpenAIService
from bot_assistant.services.telegram_notifier import TelegramNotifier
from bot_assistant.models import Lead
from bot_assistant.errors import GoogleSheetsError, OpenAIConnectionError


def _mock_config():
    """Создаёт мок для конфигурации."""
    mock_cfg = MagicMock()
    mock_cfg.google_sheets.sheets_id = "test-sheet-id"
    mock_cfg.google_sheets.credentials_file = "test-credentials.json"
    mock_cfg.google_sheets.sheets_range = "Leads!A1"
    mock_cfg.google_sheets.sheets_columns = ""
    mock_cfg.openai.api_key = "test-api-key"
    mock_cfg.openai.model = "gpt-4o-mini"
    mock_cfg.openai.temperature = 0.3
    mock_cfg.openai.max_tokens = 1024
    mock_cfg.openai.assistant_id = ""
    mock_cfg.telegram.bot_token = "test-token"
    mock_cfg.telegram.admin_chat_id = "12345"
    return mock_cfg


class TestGoogleSheetsService:
    """Тесты для GoogleSheetsService."""

    @patch("bot_assistant.services.google_sheets.service_account.Credentials")
    @patch("bot_assistant.services.google_sheets.build")
    def test_append_lead_success(self, mock_build, mock_creds):
        """Проверка успешного добавления заявки."""
        config = _mock_config()

        # Настраиваем мок Google API
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_spreadsheets = MagicMock()
        mock_service.spreadsheets.return_value = mock_spreadsheets
        mock_values = MagicMock()
        mock_spreadsheets.values.return_value = mock_values
        mock_append = MagicMock()
        mock_values.append.return_value = mock_append
        mock_append.execute.return_value = {
            "updates": {"updatedRange": "Leads!A2:J2"}
        }

        service = GoogleSheetsService(config)
        lead = Lead(
            name="Иван",
            phone="+79991234567",
            car="Toyota",
            service="Ремонт",
            desired_datetime="2026-12-25 14:00",
        )

        result = service.append_lead(lead)
        assert result["updatedRange"] == "Leads!A2:J2"

    @patch("bot_assistant.services.google_sheets.service_account.Credentials")
    @patch("bot_assistant.services.google_sheets.build")
    def test_append_lead_error(self, mock_build, mock_creds):
        """Проверка ошибки при добавлении заявки."""
        config = _mock_config()

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.spreadsheets.side_effect = Exception("API Error")

        service = GoogleSheetsService(config)
        lead = Lead(name="Иван")

        with pytest.raises(GoogleSheetsError):
            service.append_lead(lead)


class TestOpenAIService:
    """Тесты для OpenAIService."""

    @patch("bot_assistant.services.openai_service.OpenAI")
    def test_ask_success(self, mock_openai):
        """Проверка успешного запроса к OpenAI."""
        config = _mock_config()

        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_response = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_choice = MagicMock()
        mock_response.choices = [mock_choice]
        mock_choice.message.content = "Это тестовый ответ"

        service = OpenAIService(config)
        result = service.ask("Тестовый вопрос")
        assert result == "Это тестовый ответ"

    @patch("bot_assistant.services.openai_service.OpenAI")
    def test_ask_with_system(self, mock_openai):
        """Проверка запроса с системным промптом."""
        config = _mock_config()

        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_response = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_choice = MagicMock()
        mock_response.choices = [mock_choice]
        mock_choice.message.content = "Ответ с контекстом"

        service = OpenAIService(config)
        result = service.ask("Вопрос", system="Ты помощник")
        assert result == "Ответ с контекстом"

        # Проверяем, что system message был передан
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["messages"][0]["role"] == "system"


class TestTelegramNotifier:
    """Тесты для TelegramNotifier."""

    @responses.activate
    def test_send_message_success(self):
        """Проверка успешной отправки сообщения."""
        config = _mock_config()

        responses.add(
            responses.POST,
            "https://api.telegram.org/bottest-token/sendMessage",
            json={"ok": True},
            status=200,
        )

        notifier = TelegramNotifier(config)
        result = notifier.send_message("Тестовое сообщение")
        assert result is True

    @responses.activate
    def test_send_message_error(self):
        """Проверка ошибки при отправке (retry исчерпан, исключение пробрасывается)."""
        config = _mock_config()

        responses.add(
            responses.POST,
            "https://api.telegram.org/bottest-token/sendMessage",
            status=500,
        )

        notifier = TelegramNotifier(config)
        with pytest.raises(requests.HTTPError):
            notifier.send_message("Тестовое сообщение")

    def test_notify_lead(self):
        """Проверка форматирования и отправки уведомления о заявке."""
        config = _mock_config()

        notifier = TelegramNotifier(config)
        lead = Lead(
            source="telegram",
            name="Иван",
            phone="+79991234567",
            car="Toyota",
            service="Ремонт",
            desired_datetime="2026-12-25 14:00",
        )

        with patch.object(notifier, "send_message", return_value=True) as mock_send:
            result = notifier.notify_lead(lead)
            assert result is True
            mock_send.assert_called_once()
            # Проверяем, что сообщение содержит данные заявки
            call_args = mock_send.call_args[0][0]
            assert "Иван" in call_args
            assert "+79991234567" in call_args
            assert "Toyota" in call_args