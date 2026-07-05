"""
Тесты для Circuit Breaker паттерна.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from bot_assistant.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    get_circuit_breaker,
    reset_all_circuit_breakers,
)


class TestCircuitBreakerInitialState:
    """Тесты начального состояния Circuit Breaker."""

    def test_initial_state_closed(self):
        """При создании circuit breaker находится в состоянии CLOSED."""
        cb = CircuitBreaker(name="test")
        assert cb.state == CircuitState.CLOSED

    def test_initial_failure_count_zero(self):
        """При создании счётчик ошибок равен 0."""
        cb = CircuitBreaker(name="test")
        assert cb._failure_count == 0

    def test_custom_parameters(self):
        """Параметры circuit breaker настраиваются через конструктор."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=3,
            recovery_timeout=10.0,
            half_open_max_attempts=2,
        )
        assert cb.failure_threshold == 3
        assert cb.recovery_timeout == 10.0
        assert cb.half_open_max_attempts == 2


class TestCircuitBreakerClosedState:
    """Тесты поведения в состоянии CLOSED."""

    def test_successful_call_resets_failure_count(self):
        """Успешный вызов сбрасывает счётчик ошибок."""
        cb = CircuitBreaker(name="test", failure_threshold=3)
        mock_func = MagicMock(return_value="ok")

        # Несколько успешных вызовов
        for _ in range(5):
            result = cb.call(mock_func)
            assert result == "ok"

        assert cb._failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_failures_below_threshold_stay_closed(self):
        """Ошибки ниже порога не открывают circuit breaker."""
        cb = CircuitBreaker(name="test", failure_threshold=3)
        mock_func = MagicMock(side_effect=ValueError("fail"))

        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(mock_func)

        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 2

    def test_failures_reach_threshold_opens(self):
        """Достижение порога ошибок открывает circuit breaker."""
        cb = CircuitBreaker(name="test", failure_threshold=3)
        mock_func = MagicMock(side_effect=ValueError("fail"))

        for _ in range(3):
            with pytest.raises(ValueError):
                cb.call(mock_func)

        assert cb.state == CircuitState.OPEN
        assert cb._failure_count == 3

    def test_success_after_failures_resets_counter(self):
        """Успех после нескольких ошибок сбрасывает счётчик."""
        cb = CircuitBreaker(name="test", failure_threshold=3)
        fail_func = MagicMock(side_effect=ValueError("fail"))
        success_func = MagicMock(return_value="ok")

        # Две ошибки
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(fail_func)

        assert cb._failure_count == 2

        # Успех
        result = cb.call(success_func)
        assert result == "ok"
        assert cb._failure_count == 0
        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerOpenState:
    """Тесты поведения в состоянии OPEN."""

    def test_open_state_blocks_calls(self):
        """В OPEN состоянии вызовы блокируются с CircuitBreakerOpenError."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=60.0,  # Долгий таймаут, чтобы не перешёл в HALF_OPEN
        )
        mock_func = MagicMock(side_effect=ValueError("fail"))

        # Достигаем порога
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(mock_func)

        assert cb.state == CircuitState.OPEN

        # Попытка вызова в OPEN состоянии
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            cb.call(mock_func)

        assert "OPEN" in str(exc_info.value)
        assert "test" in str(exc_info.value)

    def test_open_state_recovers_after_timeout(self):
        """После recovery_timeout circuit breaker переходит в HALF_OPEN."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.01,  # Очень короткий таймаут
        )
        mock_func = MagicMock(side_effect=ValueError("fail"))

        # Достигаем порога
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(mock_func)

        assert cb.state == CircuitState.OPEN

        # Ждём восстановления
        time.sleep(0.02)

        # Должен перейти в HALF_OPEN и выполнить пробный вызов
        with pytest.raises(ValueError):
            cb.call(mock_func)

        assert cb.state == CircuitState.OPEN  # Снова OPEN, т.к. пробный упал


class TestCircuitBreakerHalfOpenState:
    """Тесты поведения в состоянии HALF_OPEN."""

    def test_half_open_success_recovers(self):
        """Успешный пробный вызов в HALF_OPEN возвращает в CLOSED."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.01,
        )
        fail_func = MagicMock(side_effect=ValueError("fail"))
        success_func = MagicMock(return_value="recovered")

        # Достигаем порога
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(fail_func)

        assert cb.state == CircuitState.OPEN

        # Ждём восстановления
        time.sleep(0.02)

        # Пробный вызов — успех
        result = cb.call(success_func)
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0

    def test_half_open_failure_reopens(self):
        """Провал пробного вызова в HALF_OPEN возвращает в OPEN."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.01,
        )
        mock_func = MagicMock(side_effect=ValueError("fail"))

        # Достигаем порога
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(mock_func)

        assert cb.state == CircuitState.OPEN

        # Ждём восстановления
        time.sleep(0.02)

        # Пробный вызов — снова ошибка
        with pytest.raises(ValueError):
            cb.call(mock_func)

        assert cb.state == CircuitState.OPEN

    def test_half_open_max_attempts(self):
        """Превышение лимита пробных вызовов в HALF_OPEN возвращает в OPEN."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.01,
            half_open_max_attempts=2,
        )
        fail_func = MagicMock(side_effect=ValueError("fail"))

        # Достигаем порога
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(fail_func)

        assert cb.state == CircuitState.OPEN

        # Ждём восстановления
        time.sleep(0.02)

        # Первый пробный — ошибка, возвращаемся в OPEN
        with pytest.raises(ValueError):
            cb.call(fail_func)

        # Ждём снова
        time.sleep(0.02)

        # Второй пробный — ошибка, превышен лимит
        with pytest.raises(ValueError):
            cb.call(fail_func)

        # Третий раз — уже OPEN, блокируется
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(fail_func)


class TestCircuitBreakerReset:
    """Тесты сброса circuit breaker."""

    def test_reset_closes_circuit(self):
        """Сброс возвращает circuit breaker в CLOSED состояние."""
        cb = CircuitBreaker(name="test", failure_threshold=2)
        mock_func = MagicMock(side_effect=ValueError("fail"))

        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(mock_func)

        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0

    def test_reset_clears_half_open_state(self):
        """Сброс работает и из HALF_OPEN состояния."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.01,
        )
        mock_func = MagicMock(side_effect=ValueError("fail"))

        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(mock_func)

        time.sleep(0.02)

        # Переход в HALF_OPEN
        with pytest.raises(ValueError):
            cb.call(mock_func)

        cb.reset()
        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerRegistry:
    """Тесты глобального реестра circuit breaker'ов."""

    def setup_method(self):
        reset_all_circuit_breakers()

    def test_get_circuit_breaker_creates_new(self):
        """get_circuit_breaker создаёт новый экземпляр, если его нет."""
        cb = get_circuit_breaker(name="test_service")
        assert cb.name == "test_service"
        assert cb.state == CircuitState.CLOSED

    def test_get_circuit_breaker_returns_same_instance(self):
        """get_circuit_breaker возвращает тот же экземпляр для одного имени."""
        cb1 = get_circuit_breaker(name="shared")
        cb2 = get_circuit_breaker(name="shared")
        assert cb1 is cb2

    def test_different_names_different_instances(self):
        """Разные имена дают разные экземпляры."""
        cb1 = get_circuit_breaker(name="service_a")
        cb2 = get_circuit_breaker(name="service_b")
        assert cb1 is not cb2

    def test_reset_all_clears_registry(self):
        """reset_all_circuit_breakers очищает реестр."""
        get_circuit_breaker(name="test")
        reset_all_circuit_breakers()
        cb = get_circuit_breaker(name="test")
        assert cb._failure_count == 0
        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerAsDecorator:
    """Тесты использования circuit breaker как декоратора."""

    def test_decorator_blocks_when_open(self):
        """Декоратор блокирует вызовы в OPEN состоянии."""
        cb = CircuitBreaker(name="decorator_test", failure_threshold=1, recovery_timeout=60.0)

        @cb
        def failing_func():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            failing_func()

        # Теперь OPEN
        with pytest.raises(CircuitBreakerOpenError):
            failing_func()

    def test_decorator_passes_successful_calls(self):
        """Декоратор пропускает успешные вызовы."""
        cb = CircuitBreaker(name="decorator_success")

        @cb
        def success_func():
            return "ok"

        result = success_func()
        assert result == "ok"


class TestCircuitBreakerThreadSafety:
    """Тесты thread-safety circuit breaker."""

    def test_concurrent_calls_dont_corrupt_state(self):
        """Параллельные вызовы не повреждают состояние."""
        import concurrent.futures

        cb = CircuitBreaker(name="thread_test", failure_threshold=3, recovery_timeout=0.01)

        def make_call(succeed: bool):
            def func():
                if not succeed:
                    raise ValueError("fail")
                return "ok"
            try:
                return cb.call(func)
            except (ValueError, CircuitBreakerOpenError):
                return "error"

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            # 3 неуспешных вызова параллельно
            for _ in range(3):
                futures.append(executor.submit(make_call, False))
            # Несколько успешных
            for _ in range(5):
                futures.append(executor.submit(make_call, True))

            results = [f.result() for f in futures]

        # После 3 ошибок circuit breaker должен был открыться
        # Но из-за параллельности может быть больше 3 ошибок
        assert cb._failure_count >= 3 or cb.state == CircuitState.OPEN