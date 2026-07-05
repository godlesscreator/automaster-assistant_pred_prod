"""
Тесты для async утилит.
"""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from bot_assistant.async_utils import run_sync, run_sync_with_timeout, shutdown_executor


class TestRunSync:
    """Тесты для run_sync."""

    @pytest.mark.asyncio
    async def test_run_sync_returns_result(self):
        """Проверка, что run_sync возвращает результат синхронной функции."""

        def sync_func(x: int, y: int) -> int:
            return x + y

        result = await run_sync(sync_func, 2, 3)
        assert result == 5

    @pytest.mark.asyncio
    async def test_run_sync_with_kwargs(self):
        """Проверка, что run_sync работает с keyword arguments."""

        def sync_func(a: str, b: str = "") -> str:
            return a + b

        result = await run_sync(sync_func, "hello", b=" world")
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_run_sync_propagates_exception(self):
        """Проверка, что исключения из синхронной функции пробрасываются."""

        def sync_func():
            raise ValueError("Sync error")

        with pytest.raises(ValueError, match="Sync error"):
            await run_sync(sync_func)

    @pytest.mark.asyncio
    async def test_run_sync_does_not_block_event_loop(self):
        """Проверка, что run_sync не блокирует event loop."""
        start = time.monotonic()

        async def async_task():
            await asyncio.sleep(0.1)
            return "done"

        def blocking_sync():
            time.sleep(0.2)
            return "blocking done"

        # Запускаем обе задачи параллельно
        results = await asyncio.gather(
            run_sync(blocking_sync),
            async_task(),
        )

        elapsed = time.monotonic() - start
        # Если бы blocking_sync блокировал event loop, elapsed было бы > 0.3
        # Но т.к. он в thread pool, задачи выполняются параллельно
        assert elapsed < 0.3  # Должно быть ~0.2, а не 0.3
        assert results == ["blocking done", "done"]


class TestRunSyncWithTimeout:
    """Тесты для run_sync_with_timeout."""

    @pytest.mark.asyncio
    async def test_run_sync_with_timeout_success(self):
        """Проверка успешного выполнения с таймаутом."""

        def sync_func():
            return "success"

        result = await run_sync_with_timeout(sync_func, timeout=5.0)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_run_sync_with_timeout_raises_on_timeout(self):
        """Проверка, что при превышении таймаута выбрасывается исключение."""

        def slow_func():
            time.sleep(10)
            return "too late"

        with pytest.raises(asyncio.TimeoutError):
            await run_sync_with_timeout(slow_func, timeout=0.1)

    @pytest.mark.asyncio
    async def test_run_sync_with_timeout_propagates_exception(self):
        """Проверка, что исключения пробрасываются."""

        def sync_func():
            raise RuntimeError("Error with timeout")

        with pytest.raises(RuntimeError, match="Error with timeout"):
            await run_sync_with_timeout(sync_func, timeout=5.0)


class TestShutdownExecutor:
    """Тесты для shutdown_executor."""

    def test_shutdown_executor_does_not_raise(self):
        """Проверка, что shutdown_executor не выбрасывает исключений."""
        try:
            shutdown_executor()
        except Exception as e:
            pytest.fail(f"shutdown_executor raised {e}")

    def test_shutdown_executor_can_be_called_multiple_times(self):
        """Проверка, что shutdown_executor можно вызывать несколько раз."""
        shutdown_executor()
        shutdown_executor()  # Второй вызов не должен упасть