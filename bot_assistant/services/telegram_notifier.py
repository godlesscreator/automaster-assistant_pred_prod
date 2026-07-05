"""
Сервис для отправки уведомлений в Telegram.
"""

from typing import Optional

import requests

from bot_assistant.config import AppConfig
from bot_assistant.errors import TelegramNotificationError
from bot_assistant.logger import get_logger
from bot_assistant.models import Lead
from bot_assistant.retry import retry

logger = get_logger(__name__)


class TelegramNotifier:
    """Сервис для отправки уведомлений в Telegram."""

    def __init__(self, config: AppConfig):
        self._config = config.telegram
        self._base_url = f"https://api.telegram.org/bot{self._config.bot_token}"

    @retry(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(requests.RequestException,))
    def _send_request(self, method: str, payload: dict) -> bool:
        """Отправляет запрос к Telegram API."""
        if not self._config.bot_token or not self._config.admin_chat_id:
            logger.warning("Telegram notifier not configured (missing token or chat_id)")
            return False

        url = f"{self._base_url}/{method}"
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.debug("Telegram API request successful: %s", method)
        return True

    def send_message(self, text: str, chat_id: Optional[str] = None) -> bool:
        """
        Отправляет текстовое сообщение.

        Args:
            text: Текст сообщения
            chat_id: ID чата (по умолчанию admin_chat_id)

        Returns:
            True если отправка успешна
        """
        payload = {
            "chat_id": chat_id or self._config.admin_chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        return self._send_request("sendMessage", payload)

    def notify_lead(self, lead: Lead) -> bool:
        """
        Отправляет уведомление о новой заявке.

        Args:
            lead: Заявка

        Returns:
            True если отправка успешна
        """
        message = self._format_lead_message(lead)
        return self.send_message(message)

    def _format_lead_message(self, lead: Lead) -> str:
        """Форматирует заявку в читаемое сообщение."""
        parts = [
            "🔔 <b>Новая заявка!</b>",
            f"📱 Источник: {lead.source}",
            f"👤 Имя: {lead.name}",
            f"📞 Телефон: {lead.phone}",
            f"🚗 Авто: {lead.car}",
            f"🔧 Услуга: {lead.service}",
            f"📅 Желаемая дата: {lead.desired_datetime}",
        ]
        if lead.comment:
            parts.append(f"💬 Комментарий: {lead.comment}")
        parts.append(f"🆔 Пользователь: {lead.user_id}")
        parts.append(f"⏰ Создано: {lead.timestamp}")
        return "\n".join(parts)

    def send_broadcast(self, text: str, chat_ids: list[str]) -> dict[str, bool]:
        """
        Отправляет сообщение нескольким получателям.

        Args:
            text: Текст сообщения
            chat_ids: Список ID чатов

        Returns:
            Словарь {chat_id: success}
        """
        results = {}
        for chat_id in chat_ids:
            results[chat_id] = self.send_message(text, chat_id)
        return results


# Для обратной совместимости
_notifier: Optional[TelegramNotifier] = None


def get_notifier() -> TelegramNotifier:
    """Прокси для обратной совместимости."""
    global _notifier
    if _notifier is None:
        from bot_assistant.di import get_container
        container = get_container()
        _notifier = container.get_notifier()
    return _notifier