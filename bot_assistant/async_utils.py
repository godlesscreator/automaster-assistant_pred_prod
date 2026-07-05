"""
Асинхронные утилиты для запуска синхронных вызовов в thread pool.
Предотвращает блокировку event loop при вызовах OpenAI, Google Sheets, Telegram API.
"""

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

from bot_assistant.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# Глобальный thread pool для синхронных вызовов
_sync_executor = ThreadPoolExecutor(
    max_workers=10,
    thread_name_prefix="sync_worker",
)


async def run_sync(func: Callable[..., T], *args, **kwargs) -> T:
    """
    Запускает синхронную функцию в thread pool, не блокируя event loop.

    Используется для:
    - OpenAI API вызовов (sync)
    - Google Sheets API вызовов (sync)
    - Telegram HTTP запросов (sync)

    Args:
        func: Синхронная функция
        *args, **kwargs: Аргументы функции

    Returns:
        Результат выполнения функции

    Пример:
        result = await run_sync(openai_service.ask, prompt="Привет")
    """
    loop = asyncio.get_running_loop()
    partial = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(_sync_executor, partial)


async def run_sync_with_timeout(
    func: Callable[..., T],
    timeout: float = 30.0,
    *args,
    **kwargs,
) -> T:
    """
    Запускает синхронную функцию в thread pool с таймаутом.

    Args:
        func: Синхронная функция
        timeout: Таймаут в секундах
        *args, **kwargs: Аргументы функции

    Returns:
        Результат выполнения функции

    Raises:
        asyncio.TimeoutError: Если функция не завершилась за timeout секунд
    """
    loop = asyncio.get_running_loop()
    partial = functools.partial(func, *args, **kwargs)
    return await asyncio.wait_for(
        loop.run_in_executor(_sync_executor, partial),
        timeout=timeout,
    )


def shutdown_executor():
    """Завершает thread pool (вызывается при graceful shutdown)."""
    _sync_executor.shutdown(wait=True, cancel_futures=False)
    logger.info("Sync executor shut down")