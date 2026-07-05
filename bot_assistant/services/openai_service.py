"""
Сервис для работы с OpenAI API.
"""

from typing import Optional

from openai import OpenAI

from bot_assistant.circuit_breaker import (
    CircuitBreakerOpenError,
    get_circuit_breaker,
)
from bot_assistant.config import AppConfig
from bot_assistant.errors import OpenAIConnectionError
from bot_assistant.logger import get_logger
from bot_assistant.retry import retry

logger = get_logger(__name__)


class OpenAIService:
    """Сервис для работы с OpenAI API."""

    def __init__(self, config: AppConfig):
        self._config = config.openai
        self._client = None
        self._circuit_breaker = get_circuit_breaker(
            name="openai",
            failure_threshold=5,
            recovery_timeout=30.0,
            half_open_max_attempts=3,
        )

    def _get_client(self) -> OpenAI:
        """Возвращает клиент OpenAI (с ленивой инициализацией)."""
        if self._client is None:
            if not self._config.api_key:
                raise OpenAIConnectionError("OPENAI_API_KEY не настроен")
            self._client = OpenAI(api_key=self._config.api_key)
            logger.debug("OpenAI client initialized")
        return self._client

    @retry(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(OpenAIConnectionError,))
    def ask(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Отправляет запрос к OpenAI и возвращает ответ.

        Args:
            prompt: Текст запроса пользователя
            system: Системный промпт (опционально)
            temperature: Температура генерации (0.0 - 1.0)
            max_tokens: Максимальное количество токенов в ответе

        Returns:
            Текст ответа

        Raises:
            OpenAIConnectionError: При ошибке запроса или если circuit breaker открыт
        """
        try:
            return self._circuit_breaker.call(self._ask_impl, prompt, system, temperature, max_tokens)
        except CircuitBreakerOpenError as e:
            logger.warning("OpenAI circuit breaker open: %s", e)
            raise OpenAIConnectionError(
                "Сервис OpenAI временно недоступен. Попробуйте позже."
            )

    def _ask_impl(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Внутренняя реализация запроса к OpenAI (без circuit breaker)."""
        try:
            client = self._get_client()
            messages = []

            if system:
                messages.append({"role": "system", "content": system})

            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self._config.model,
                messages=messages,
                temperature=temperature or self._config.temperature,
                max_tokens=max_tokens or self._config.max_tokens,
            )

            content = response.choices[0].message.content or ""
            logger.debug("OpenAI response received (%d chars)", len(content))
            return content

        except OpenAIConnectionError:
            raise
        except Exception as e:
            logger.error("OpenAI request failed: %s", e)
            raise OpenAIConnectionError(f"Ошибка запроса к OpenAI: {e}")

    @retry(max_attempts=2, delay=2.0, backoff=2.0, exceptions=(OpenAIConnectionError,))
    def ask_assistant(
        self,
        message: str,
        thread_id: Optional[str] = None,
    ) -> tuple[str, Optional[str]]:
        """
        Отправляет запрос через OpenAI Assistant (Threads API).

        Args:
            message: Текст сообщения
            thread_id: ID существующего треда (опционально)

        Returns:
            Кортеж (ответ, thread_id)

        Raises:
            OpenAIConnectionError: При ошибке запроса или если circuit breaker открыт
        """
        if not self._config.assistant_id:
            raise OpenAIConnectionError("OPENAI_ASSISTANT_ID не настроен")

        try:
            return self._circuit_breaker.call(
                self._ask_assistant_impl, message, thread_id
            )
        except CircuitBreakerOpenError as e:
            logger.warning("OpenAI circuit breaker open: %s", e)
            raise OpenAIConnectionError(
                "Сервис OpenAI временно недоступен. Попробуйте позже."
            )

    def _ask_assistant_impl(
        self,
        message: str,
        thread_id: Optional[str] = None,
    ) -> tuple[str, Optional[str]]:
        """Внутренняя реализация запроса к Assistant API (без circuit breaker)."""
        try:
            client = self._get_client()

            # Создаём или используем существующий тред
            if thread_id:
                thread = client.beta.threads.retrieve(thread_id)
            else:
                thread = client.beta.threads.create()

            # Добавляем сообщение
            client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=message,
            )

            # Запускаем ассистента
            run = client.beta.threads.runs.create_and_poll(
                thread_id=thread.id,
                assistant_id=self._config.assistant_id,
            )

            if run.status == "completed":
                messages = client.beta.threads.messages.list(
                    thread_id=thread.id
                )
                for msg in messages.data:
                    if msg.role == "assistant":
                        content = "".join(
                            block.text.value
                            for block in msg.content
                            if hasattr(block, "text")
                        )
                        return content, thread.id

            return "Не удалось получить ответ от ассистента.", thread.id

        except Exception as e:
            logger.error("OpenAI Assistant request failed: %s", e)
            raise OpenAIConnectionError(f"Ошибка запроса к Assistant: {e}")


# Для обратной совместимости
_openai_service: Optional[OpenAIService] = None


def get_openai_service() -> OpenAIService:
    """Прокси для обратной совместимости."""
    global _openai_service
    if _openai_service is None:
        from bot_assistant.di import get_container
        container = get_container()
        _openai_service = container.get_openai_service()
    return _openai_service