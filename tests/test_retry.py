"""
Тесты для retry-механизмов.
"""

import pytest
from unittest.mock import MagicMock, patch

from bot_assistant.retry import retry, retry_async


class TestRetrySync:
    """Тесты для синхронного retry-декоратора."""

    def test_retry_success_first_attempt(self):
        """Проверка, что функция выполняется с первого раза."""
        mock_func = MagicMock(return_value="success")

        @retry(max_attempts=3, delay=0.01, backoff=1.0)
        def test_func():
            return mock_func()

        result = test_func()
        assert result == "success"
        assert mock_func.call_count == 1

    def test_retry_success_after_failures(self):
        """Проверка, что retry срабатывает после ошибок."""
        call_count = 0

        @retry(max_attempts=3, delay=0.01, backoff=1.0)
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == 3

    def test_retry_fails_after_max_attempts(self):
        """Проверка, что после max_attempts ошибка пробрасывается."""
        call_count = 0

        @retry(max_attempts=3, delay=0.01, backoff=1.0)
        def test_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Persistent error")

        with pytest.raises(ValueError, match="Persistent error"):
            test_func()
        assert call_count == 3

    def test_retry_only_specific_exceptions(self):
        """Проверка, что retry срабатывает только на указанные исключения."""
        @retry(max_attempts=3, delay=0.01, backoff=1.0, exceptions=(ValueError,))
        def test_func():
            raise TypeError("Wrong exception type")

        with pytest.raises(TypeError):
            test_func()

    def test_retry_exponential_backoff(self):
        """Проверка exponential backoff (задержка увеличивается)."""
        call_count = 0
        delays = []

        def on_retry(attempt, delay, exc):
            delays.append(delay)

        @retry(max_attempts=4, delay=0.1, backoff=2.0, on_retry=on_retry)
        def test_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Error")

        with pytest.raises(ValueError):
            test_func()

        # Задержки: 0.1, 0.2, 0.4 (3 retry-попытки)
        assert len(delays) == 3
        assert delays[0] == 0.1
        assert delays[1] == 0.2
        assert delays[2] == 0.4


class TestRetryAsync:
    """Тесты для асинхронного retry-декоратора."""

    @pytest.mark.asyncio
    async def test_retry_async_success_first_attempt(self):
        """Проверка, что async функция выполняется с первого раза."""
        mock_func = MagicMock(return_value="success")

        @retry_async(max_attempts=3, delay=0.01, backoff=1.0)
        async def test_func():
            return mock_func()

        result = await test_func()
        assert result == "success"
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_async_success_after_failures(self):
        """Проверка, что async retry срабатывает после ошибок."""
        call_count = 0

        @retry_async(max_attempts=3, delay=0.01, backoff=1.0)
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"

        result = await test_func()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_async_fails_after_max_attempts(self):
        """Проверка, что async retry пробрасывает ошибку после max_attempts."""
        call_count = 0

        @retry_async(max_attempts=2, delay=0.01, backoff=1.0)
        async def test_func():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Async error")

        with pytest.raises(RuntimeError, match="Async error"):
            await test_func()
        assert call_count == 2