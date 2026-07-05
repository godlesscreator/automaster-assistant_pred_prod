"""
Утилиты для повторных попыток (retry) при сбоях внешних сервисов.
Предотвращает потерю заявок при временных ошибках Google Sheets, OpenAI, Telegram API.
"""

import asyncio
import functools
import time
from typing import Callable, Optional, Tuple, Type

from bot_assistant.logger import get_logger

logger = get_logger(__name__)


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None,
):
    """
    Декоратор для повторных попыток выполнения функции при ошибках.
    Использует exponential backoff: 1s, 2s, 4s, 8s...

    Args:
        max_attempts: Максимальное количество попыток (включая первую)
        delay: Начальная задержка между попытками (сек)
        backoff: Множитель задержки (каждая следующая попытка ждёт дольше)
        exceptions: Кортеж исключений, при которых делать retry
        on_retry: Функция, вызываемая перед каждой повторной попыткой

    Пример:
        @retry(max_attempts=3, delay=1.0, backoff=2.0)
        def call_google_sheets():
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < max_attempts:
                        logger.warning(
                            "%s failed (attempt %d/%d): %s. Retrying in %.1fs...",
                            func.__name__, attempt, max_attempts, e, current_delay,
                        )
                        if on_retry:
                            on_retry(attempt, current_delay, e)
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            "%s failed after %d attempts: %s",
                            func.__name__, max_attempts, e,
                        )

            raise last_exception

        return wrapper
    return decorator


def retry_async(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    Декоратор для повторных попыток асинхронных функций.
    Используется для Telegram бота (async handlers).

    Args:
        max_attempts: Максимальное количество попыток
        delay: Начальная задержка между попытками (сек)
        backoff: Множитель задержки
        exceptions: Кортеж исключений, при которых делать retry
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < max_attempts:
                        logger.warning(
                            "%s failed (attempt %d/%d): %s. Retrying in %.1fs...",
                            func.__name__, attempt, max_attempts, e, current_delay,
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            "%s failed after %d attempts: %s",
                            func.__name__, max_attempts, e,
                        )

            raise last_exception

        return wrapper
    return decorator