"""
Модуль безопасности приложения.
Содержит:
- CSRF-защита для веб-чата
- Rate limiting для админ-панели (brute-force защита)
- Проверка Origin для API
"""

import hashlib
import hmac
import logging
import time
from typing import Dict, Optional, Tuple

from bot_assistant.config import get_config
from bot_assistant.redis_client import get_redis

logger = logging.getLogger(__name__)

# In-memory fallback для rate limiting (когда Redis недоступен)
_LOGIN_ATTEMPTS: Dict[str, list] = {}


# ============================================================
# CSRF Protection
# ============================================================

def generate_csrf_token(session_id: str) -> str:
    """
    Генерирует CSRF-токен для сессии веб-чата.

    Токен создаётся на основе session_id и секретного ключа приложения.
    Это предотвращает подделку межсайтовых запросов (CSRF).

    Args:
        session_id: ID сессии веб-чата

    Returns:
        CSRF-токен в виде hex-строки
    """
    config = get_config()
    secret = config.flask.secret_key
    msg = f"csrf:{session_id}:{secret}"
    return hashlib.sha256(msg.encode()).hexdigest()


def validate_csrf_token(session_id: str, token: str) -> bool:
    """
    Проверяет CSRF-токен.

    Использует constant-time comparison для предотвращения timing attacks.

    Args:
        session_id: ID сессии веб-чата
        token: CSRF-токен из запроса

    Returns:
        True если токен валидный
    """
    expected = generate_csrf_token(session_id)
    return hmac.compare_digest(expected, token)


def csrf_required(session_id: str, token: Optional[str]) -> Tuple[bool, str]:
    """
    Проверяет наличие и валидность CSRF-токена.

    Args:
        session_id: ID сессии
        token: CSRF-токен из запроса (может быть None)

    Returns:
        (is_valid, error_message)
    """
    if not token:
        return False, "CSRF-токен отсутствует. Обновите страницу и попробуйте снова."

    if not validate_csrf_token(session_id, token):
        return False, "Неверный CSRF-токен. Возможно, сессия устарела."

    return True, ""


# ============================================================
# Rate Limiting (Brute-force protection)
# ============================================================

def check_login_rate_limit(
    username: str,
    ip_address: str,
    max_attempts: int = 5,
    window_seconds: int = 900,  # 15 минут
    block_duration: int = 1800,  # 30 минут блокировки
) -> Tuple[bool, Optional[str]]:
    """
    Проверяет rate limit для попыток входа в админ-панель.

    Блокирует IP после N неудачных попыток за временное окно.

    Args:
        username: Имя пользователя
        ip_address: IP адрес клиента
        max_attempts: Максимальное количество попыток
        window_seconds: Временное окно в секундах
        block_duration: Длительность блокировки в секундах

    Returns:
        (is_allowed, error_message)
    """
    redis = get_redis()
    key = f"login_attempts:{ip_address}:{username}"
    block_key = f"login_blocked:{ip_address}"

    # Проверяем, не заблокирован ли IP
    if redis.enabled:
        is_blocked = redis.cache_get(block_key)
        if is_blocked:
            return False, "Слишком много попыток входа. Попробуйте через 30 минут."
    else:
        if ip_address in _LOGIN_ATTEMPTS:
            blocks = _LOGIN_ATTEMPTS[ip_address]
            if blocks and isinstance(blocks[0], dict) and blocks[0].get("blocked"):
                if time.time() - blocks[0]["timestamp"] < block_duration:
                    return False, "Слишком много попыток входа. Попробуйте через 30 минут."
                else:
                    _LOGIN_ATTEMPTS.pop(ip_address, None)

    return True, None


def record_failed_login(username: str, ip_address: str) -> None:
    """
    Фиксирует неудачную попытку входа.

    Args:
        username: Имя пользователя
        ip_address: IP адрес клиента
    """
    redis = get_redis()
    key = f"login_attempts:{ip_address}:{username}"
    block_key = f"login_blocked:{ip_address}"

    if redis.enabled:
        current = redis.cache_get(key)
        count = 1
        if current:
            try:
                count = int(current) + 1
            except (ValueError, TypeError):
                count = 1

        redis.cache_set(key, str(count), ttl=900)  # 15 минут

        if count >= 5:
            redis.cache_set(block_key, "1", ttl=1800)  # 30 минут блокировки
            logger.warning(
                "Login blocked for IP %s (username: %s) after %d failed attempts",
                ip_address, username, count,
            )
    else:
        now = time.time()
        if ip_address not in _LOGIN_ATTEMPTS:
            _LOGIN_ATTEMPTS[ip_address] = []

        _LOGIN_ATTEMPTS[ip_address].append({
            "username": username,
            "timestamp": now,
        })

        # Очищаем старые записи (старше 15 минут)
        _LOGIN_ATTEMPTS[ip_address] = [
            a for a in _LOGIN_ATTEMPTS[ip_address]
            if now - a["timestamp"] < 900
        ]

        # Блокируем если больше 5 попыток
        if len(_LOGIN_ATTEMPTS[ip_address]) >= 5:
            _LOGIN_ATTEMPTS[ip_address] = [{"blocked": True, "timestamp": now}]
            logger.warning(
                "Login blocked for IP %s (username: %s) after %d failed attempts (in-memory)",
                ip_address, username, len(_LOGIN_ATTEMPTS[ip_address]),
            )

    logger.warning(
        "Failed login attempt for username '%s' from IP %s",
        username, ip_address,
    )


def record_successful_login(username: str, ip_address: str) -> None:
    """
    Сбрасывает счётчик попыток после успешного входа.

    Args:
        username: Имя пользователя
        ip_address: IP адрес клиента
    """
    redis = get_redis()
    key = f"login_attempts:{ip_address}:{username}"

    if redis.enabled:
        redis.cache_set(key, "0", ttl=1)
    else:
        _LOGIN_ATTEMPTS.pop(ip_address, None)

    logger.info("Successful login for username '%s' from IP %s", username, ip_address)


# ============================================================
# Origin Check для API
# ============================================================

def check_origin(allowed_origins: Optional[list] = None) -> Tuple[bool, str]:
    """
    Проверяет заголовок Origin/Referer для защиты от CSRF через API.

    Должна вызываться в начале обработки POST/PATCH/DELETE запросов.

    Args:
        allowed_origins: Список разрешённых источников.
                        Если None — используется WEB_ORIGIN из конфига.

    Returns:
        (is_valid, error_message)
    """
    from flask import request

    if allowed_origins is None:
        config = get_config()
        allowed_origins = [config.flask.web_origin]

    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")

    # Если заголовков нет — пропускаем (старые клиенты)
    if not origin and not referer:
        return True, ""

    source = origin or referer

    # Проверяем, что источник в списке разрешённых
    for allowed in allowed_origins:
        if source.startswith(allowed):
            return True, ""

    logger.warning(
        "Origin check failed: source=%s, allowed=%s",
        source, allowed_origins,
    )
    return False, f"Запрос с неподдерживаемого источника: {source}"