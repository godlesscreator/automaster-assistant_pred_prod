"""
Модуль кастомных исключений.
"""


class BotAssistantError(Exception):
    """Базовое исключение для всех ошибок приложения."""
    pass


class ConfigurationError(BotAssistantError):
    """Ошибка конфигурации (отсутствуют обязательные переменные)."""
    pass


class GoogleSheetsError(BotAssistantError):
    """Ошибка при работе с Google Sheets."""
    pass


class OpenAIConnectionError(BotAssistantError):
    """Ошибка при запросе к OpenAI."""
    pass


class TelegramNotificationError(BotAssistantError):
    """Ошибка при отправке уведомления в Telegram."""
    pass


class ValidationError(BotAssistantError):
    """Ошибка валидации данных."""
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


class LeadSaveError(BotAssistantError):
    """Ошибка сохранения заявки."""
    pass


class RateLimitError(BotAssistantError):
    """Превышен лимит запросов."""
    pass