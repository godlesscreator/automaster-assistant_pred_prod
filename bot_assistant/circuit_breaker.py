"""
Circuit Breaker паттерн для защиты внешних вызовов.

Предотвращает каскадные сбои: если внешний сервис (OpenAI, Google Sheets)
начинает падать, circuit breaker временно отключает вызовы к нему,
давая сервису время восстановиться.

Состояния:
- CLOSED (закрыт) — нормальная работа, вызовы проходят
- OPEN (открыт) — вызовы блокируются, возвращается fallback/ошибка
- HALF_OPEN (полуоткрыт) — пробный вызов для проверки восстановления

Пороги настраиваются через конфигурацию:
- failure_threshold: количество ошибок для открытия (по умолч. 5)
- recovery_timeout: время в секундах до пробного вызова (по умолч. 30)
- half_open_max_attempts: макс. пробных вызовов в HALF_OPEN (по умолч. 3)
"""

import threading
import time
from enum import Enum
from typing import Callable, Optional, TypeVar

from bot_assistant.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Состояния circuit breaker."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Thread-safe Circuit Breaker для защиты внешних вызовов.

    Пример:
        cb = CircuitBreaker(name="openai", failure_threshold=5, recovery_timeout=30)
        with cb:
            result = call_openai_api()
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_attempts: int = 3,
    ):
        """
        Args:
            name: Имя сервиса (для логов)
            failure_threshold: Количество последовательных ошибок для открытия
            recovery_timeout: Секунд до перехода в HALF_OPEN
            half_open_max_attempts: Макс. пробных вызовов в HALF_OPEN
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_attempts = half_open_max_attempts

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_attempts = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        """Текущее состояние circuit breaker."""
        with self._lock:
            return self._state

    def _should_attempt_recovery(self) -> bool:
        """Проверяет, прошло ли достаточно времени для пробного вызова."""
        if self._last_failure_time is None:
            return True
        elapsed = time.monotonic() - self._last_failure_time
        return elapsed >= self.recovery_timeout

    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Выполняет функцию с защитой circuit breaker.

        Args:
            func: Функция для вызова
            *args, **kwargs: Аргументы функции

        Returns:
            Результат вызова функции

        Raises:
            CircuitBreakerOpenError: Если circuit breaker открыт
            Исходное исключение функции при ошибке
        """
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_recovery():
                    logger.info(
                        "Circuit breaker '%s' transitioning OPEN -> HALF_OPEN "
                        "(recovery timeout elapsed)",
                        self.name,
                    )
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_attempts = 0
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is OPEN. "
                        f"Service unavailable. Retry in "
                        f"{self.recovery_timeout - (time.monotonic() - self._last_failure_time):.0f}s"
                    )

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_attempts >= self.half_open_max_attempts:
                    logger.warning(
                        "Circuit breaker '%s': max half-open attempts (%d) reached, "
                        "reopening circuit",
                        self.name,
                        self.half_open_max_attempts,
                    )
                    self._state = CircuitState.OPEN
                    self._last_failure_time = time.monotonic()
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is OPEN "
                        f"(max half-open attempts reached)"
                    )
                self._half_open_attempts += 1

        # Выполняем функцию вне блокировки
        try:
            result = func(*args, **kwargs)
        except Exception as e:
            with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.monotonic()

                if self._failure_count >= self.failure_threshold:
                    if self._state != CircuitState.OPEN:
                        logger.warning(
                            "Circuit breaker '%s' OPENING after %d failures "
                            "(threshold: %d). Last error: %s",
                            self.name,
                            self._failure_count,
                            self.failure_threshold,
                            e,
                        )
                        self._state = CircuitState.OPEN
                else:
                    logger.debug(
                        "Circuit breaker '%s': failure %d/%d",
                        self.name,
                        self._failure_count,
                        self.failure_threshold,
                    )
            raise

        # Успех — сбрасываем счётчик
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(
                    "Circuit breaker '%s' recovered (HALF_OPEN -> CLOSED)",
                    self.name,
                )
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_attempts = 0
            self._last_failure_time = None

        return result

    def reset(self) -> None:
        """Принудительный сброс circuit breaker (для тестов)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_attempts = 0
            self._last_failure_time = None
            logger.debug("Circuit breaker '%s' reset to CLOSED", self.name)

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Позволяет использовать circuit breaker как декоратор."""
        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)
        return wrapper


class CircuitBreakerOpenError(Exception):
    """Исключение, когда circuit breaker открыт и блокирует вызов."""
    pass


# Глобальный реестр circuit breaker'ов
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    half_open_max_attempts: int = 3,
) -> CircuitBreaker:
    """
    Возвращает или создаёт circuit breaker с указанным именем.

    Args:
        name: Имя сервиса
        failure_threshold: Количество ошибок для открытия
        recovery_timeout: Время до пробного вызова (сек)
        half_open_max_attempts: Макс. пробных вызовов

    Returns:
        Экземпляр CircuitBreaker
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_attempts=half_open_max_attempts,
        )
    return _circuit_breakers[name]


def reset_all_circuit_breakers() -> None:
    """Сбрасывает все circuit breaker'ы (для тестов)."""
    for cb in _circuit_breakers.values():
        cb.reset()
    _circuit_breakers.clear()