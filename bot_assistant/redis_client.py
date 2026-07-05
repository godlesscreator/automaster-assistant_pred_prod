"""
Redis клиент для кеширования сессий и rate limiting.
Используется как замена in-memory Dict для веб-сессий чата.
"""

import json
import time
from typing import Any, Dict, Optional

from bot_assistant.config import AppConfig
from bot_assistant.logger import get_logger

logger = get_logger(__name__)


class RedisClient:
    """
    Клиент для работы с Redis.
    Поддерживает:
    - Хранение сессий веб-чата
    - Rate limiting (счётчики запросов)
    - Кеширование ответов OpenAI

    Создаётся через DI контейнер. Не использует глобальные переменные.
    """

    def __init__(self, config: Optional[AppConfig] = None):
        self._client = None
        self._enabled = False
        self._config = config

    def _get_config(self) -> Optional[AppConfig]:
        """Возвращает конфигурацию."""
        if self._config is None:
            from bot_assistant.config import get_config
            self._config = get_config()
        return self._config

    def _connect(self):
        """Ленивое подключение к Redis."""
        if self._client is not None:
            return self._client

        config = self._get_config()
        if config is None or not config.redis.enabled:
            self._enabled = False
            return None

        try:
            import redis as redis_module
            self._client = redis_module.from_url(
                config.redis.url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            self._client.ping()
            self._enabled = True
            logger.info("Redis connected: %s", config.redis.url)
        except Exception as e:
            logger.warning("Redis connection failed (fallback to in-memory): %s", e)
            self._enabled = False
            self._client = None

        return self._client

    @property
    def enabled(self) -> bool:
        """Проверяет, доступен ли Redis."""
        if self._client is None:
            self._connect()
        return self._enabled

    # ---- Session management ----

    def set_session(self, session_id: str, data: dict, ttl: int = 3600) -> bool:
        """
        Сохраняет сессию в Redis.

        Args:
            session_id: ID сессии
            data: Данные сессии
            ttl: Время жизни в секундах (по умолчанию 1 час)

        Returns:
            True если успешно
        """
        client = self._connect()
        if client is None:
            return False

        try:
            client.setex(
                f"session:{session_id}",
                ttl,
                json.dumps(data, ensure_ascii=False),
            )
            return True
        except Exception as e:
            logger.warning("Redis set_session failed: %s", e)
            return False

    def get_session(self, session_id: str) -> Optional[dict]:
        """
        Получает сессию из Redis.

        Args:
            session_id: ID сессии

        Returns:
            Данные сессии или None
        """
        client = self._connect()
        if client is None:
            return None

        try:
            data = client.get(f"session:{session_id}")
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning("Redis get_session failed: %s", e)
            return None

    def delete_session(self, session_id: str) -> bool:
        """Удаляет сессию из Redis."""
        client = self._connect()
        if client is None:
            return False

        try:
            client.delete(f"session:{session_id}")
            return True
        except Exception as e:
            logger.warning("Redis delete_session failed: %s", e)
            return False

    def session_exists(self, session_id: str) -> bool:
        """Проверяет существование сессии."""
        client = self._connect()
        if client is None:
            return False

        try:
            return bool(client.exists(f"session:{session_id}"))
        except Exception as e:
            logger.warning("Redis session_exists failed: %s", e)
            return False

    # ---- Rate limiting ----

    def check_rate_limit(self, key: str, max_requests: int = 30, window: int = 60) -> bool:
        """
        Проверяет rate limit для ключа.

        Args:
            key: Ключ (например, IP адрес)
            max_requests: Максимальное количество запросов
            window: Временное окно в секундах

        Returns:
            True если запрос разрешён
        """
        client = self._connect()
        if client is None:
            return True  # Если Redis недоступен — пропускаем

        try:
            redis_key = f"ratelimit:{key}"
            current = client.get(redis_key)

            if current is None:
                client.setex(redis_key, window, 1)
                return True

            count = int(current)
            if count >= max_requests:
                return False

            client.incr(redis_key)
            return True
        except Exception as e:
            logger.warning("Redis rate limit check failed: %s", e)
            return True

    # ---- Cache ----

    def cache_get(self, key: str) -> Optional[str]:
        """Получает значение из кеша."""
        client = self._connect()
        if client is None:
            return None

        try:
            return client.get(f"cache:{key}")
        except Exception as e:
            logger.warning("Redis cache_get failed: %s", e)
            return None

    def cache_set(self, key: str, value: str, ttl: int = 300) -> bool:
        """
        Сохраняет значение в кеш.

        Args:
            key: Ключ кеша
            value: Значение
            ttl: Время жизни в секундах
        """
        client = self._connect()
        if client is None:
            return False

        try:
            client.setex(f"cache:{key}", ttl, value)
            return True
        except Exception as e:
            logger.warning("Redis cache_set failed: %s", e)
            return False

    def close(self):
        """Закрывает соединение с Redis."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
            self._enabled = False
            logger.info("Redis connection closed")


# Для обратной совместимости — функции-прокси
_redis_client: Optional[RedisClient] = None


def get_redis() -> RedisClient:
    """Прокси для обратной совместимости. Использует DI контейнер."""
    global _redis_client
    if _redis_client is None:
        from bot_assistant.di import get_container
        container = get_container()
        if container.redis:
            _redis_client = container.redis
        else:
            _redis_client = RedisClient()
    return _redis_client


def close_redis():
    """Прокси для обратной совместимости."""
    global _redis_client
    if _redis_client:
        _redis_client.close()
        _redis_client = None