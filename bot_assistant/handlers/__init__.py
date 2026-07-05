"""
Инициализация обработчиков.
Ленивые импорты для избежания циклических зависимостей.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot_assistant.handlers.telegram_bot import build_application
    from bot_assistant.handlers.web_chat import webchat_bp
    from bot_assistant.handlers.admin_panel import admin_bp
    from bot_assistant.handlers.api_v1 import api_v1_bp
    from bot_assistant.handlers.docs import docs_bp


def build_application():
    """Ленивый импорт для Telegram бота."""
    from bot_assistant.handlers.telegram_bot import build_application as _build
    return _build()


def get_webchat_bp():
    """Ленивый импорт для веб-чата."""
    from bot_assistant.handlers.web_chat import webchat_bp
    return webchat_bp


def get_admin_bp():
    """Ленивый импорт для админ-панели."""
    from bot_assistant.handlers.admin_panel import admin_bp
    return admin_bp


def get_api_v1_bp():
    """Ленивый импорт для API v1."""
    from bot_assistant.handlers.api_v1 import api_v1_bp
    return api_v1_bp


def get_docs_bp():
    """Ленивый импорт для документации."""
    from bot_assistant.handlers.docs import docs_bp
    return docs_bp


__all__ = [
    "build_application",
    "get_webchat_bp",
    "get_admin_bp",
    "get_api_v1_bp",
    "get_docs_bp",
]