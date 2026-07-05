"""
Обработчики веб-чата (Flask endpoints).
"""

from typing import Dict, Optional

from flask import Blueprint, request, jsonify

from bot_assistant.logger import get_logger
from bot_assistant.models import Lead, WebSession
from bot_assistant.redis_client import get_redis
from bot_assistant.security import (
    generate_csrf_token,
    csrf_required,
    check_origin,
)
from bot_assistant.services import get_lead_repository, get_notifier
from bot_assistant.validators import (
    validate_lead_data,
    normalize_phone,
    ValidationError,
)

logger = get_logger(__name__)

# Создаём Blueprint для веб-чата
webchat_bp = Blueprint("webchat", __name__)

# In-memory хранилище сессий (как fallback если Redis недоступен)
WEB_SESSIONS: Dict[str, WebSession] = {}

# Промпты для каждого шага
PROMPTS = {
    "name": "Как вас зовут?",
    "phone": "Ваш номер телефона?",
    "car": "Марка и модель автомобиля?",
    "service": "Какая услуга нужна? (ТО, ремонт, диагностика, покраска и др.)",
    "desired_datetime": "Желаемая дата/время визита?",
    "comment": "Добавите комментарий? Если нет — напишите: нет",
}

REQUIRED_FIELDS = ["name", "phone", "car", "service", "desired_datetime"]


def _get_or_create_session(session_id: str) -> WebSession:
    """Получает или создаёт сессию (с поддержкой Redis)."""
    redis = get_redis()

    # Пробуем Redis
    if redis.enabled:
        data = redis.get_session(session_id)
        if data:
            session = WebSession(session_id=session_id)
            for key, value in data.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            return session

    # Fallback на in-memory
    if session_id not in WEB_SESSIONS:
        WEB_SESSIONS[session_id] = WebSession(session_id=session_id)
    return WEB_SESSIONS[session_id]


def _save_session(session_id: str, session: WebSession):
    """Сохраняет сессию (в Redis или in-memory)."""
    redis = get_redis()
    data = session.to_dict()

    if redis.enabled:
        redis.set_session(session_id, data, ttl=3600)
    else:
        WEB_SESSIONS[session_id] = session


def _delete_session(session_id: str):
    """Удаляет сессию."""
    redis = get_redis()
    if redis.enabled:
        redis.delete_session(session_id)
    WEB_SESSIONS.pop(session_id, None)


def _next_required_missing(state: dict) -> Optional[str]:
    """Возвращает следующее обязательное незаполненное поле."""
    for key in REQUIRED_FIELDS:
        if not state.get(key):
            return key
    return None


@webchat_bp.route("/webchat", methods=["POST"])
def webchat():
    """
    Основной эндпоинт веб-чата.
    Принимает JSON с полями: message, user_id, name, phone, car, service, desired_datetime, comment

    CSRF-защита: требуется csrf_token в теле запроса.
    """
    try:
        payload: dict = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"error": "invalid JSON"}), 400

    user_message = (payload.get("message") or "").strip()
    session_id = (
        payload.get("user_id")
        or request.headers.get("X-Forwarded-For")
        or request.remote_addr
        or "web"
    )

    # CSRF-защита: проверяем токен, если диалог уже начат (ожидается поле)
    csrf_token = payload.get("csrf_token")
    session = _get_or_create_session(session_id)

    # CSRF проверяется только когда сессия уже в процессе (awaiting установлен)
    # Первый запрос (начало диалога) не требует CSRF
    if session.awaiting is not None:
        is_valid, error_msg = csrf_required(session_id, csrf_token)
        if not is_valid:
            logger.warning(
                "CSRF validation failed for session %s: %s",
                session_id, error_msg,
            )
            return jsonify({
                "reply": "❌ Ошибка безопасности. Обновите страницу и попробуйте снова.",
                "lead_saved": False,
                "missing_fields": [],
                "error": error_msg,
            }), 403

    state = session.to_dict()

    # Применяем явно переданные поля формы
    for key in ["name", "phone", "car", "service", "desired_datetime", "comment"]:
        if payload.get(key):
            state[key] = payload[key]

    if state.get("phone"):
        state["phone"] = normalize_phone(state["phone"])

    # Обрабатываем сообщение, если ожидаем поле
    awaiting = state.get("awaiting")
    if user_message and awaiting in PROMPTS:
        value = user_message
        if awaiting == "phone":
            value = normalize_phone(user_message)
        if awaiting == "comment" and value.lower() in ("нет", "no", "-", "нема"):
            value = ""
        state[awaiting] = value
        state["awaiting"] = None

    # Обновляем сессию
    for key in state:
        setattr(session, key, state[key])
    _save_session(session_id, session)

    # Определяем следующий шаг
    next_required = _next_required_missing(state)
    if next_required:
        state["awaiting"] = next_required
        session.awaiting = next_required
        _save_session(session_id, session)
        return jsonify({
            "reply": PROMPTS[next_required],
            "lead_saved": False,
            "missing_fields": [next_required],
            "error": "",
            "csrf_token": generate_csrf_token(session_id),
        })

    # Если все обязательные поля заполнены, спрашиваем комментарий
    if state.get("comment") is None or state.get("comment", "") == "":
        if awaiting != "comment":
            state["awaiting"] = "comment"
            session.awaiting = "comment"
            _save_session(session_id, session)
            return jsonify({
                "reply": PROMPTS["comment"],
                "lead_saved": False,
                "missing_fields": [],
                "error": "",
                "csrf_token": generate_csrf_token(session_id),
            })

    # Сохраняем заявку
    lead = Lead(
        source="tilda_web_widget",
        name=state["name"],
        phone=state["phone"],
        car=state["car"],
        service=state["service"],
        desired_datetime=state["desired_datetime"],
        comment=state.get("comment", ""),
        user_id=session_id,
    )

    lead_saved = False
    error_text = ""

    try:
        repo = get_lead_repository()
        repo.add(lead)

        notifier = get_notifier()
        notifier.notify_lead(lead)

        lead_saved = True
        answer = "✅ Спасибо! Ваша заявка принята. Мы свяжемся с вами."
        _delete_session(session_id)
        logger.info("Webchat: lead saved for session %s", session_id)

    except Exception as e:
        lead_saved = False
        error_text = f"save_error: {e}"
        answer = "❌ Произошла ошибка при сохранении заявки. Попробуйте позже."
        logger.exception("Webchat: failed to save lead: %s", e)

    return jsonify({
        "reply": answer,
        "lead_saved": lead_saved,
        "missing_fields": [],
        "error": error_text,
    })


@webchat_bp.route("/webchat/status", methods=["GET"])
def webchat_status():
    """Возвращает статус веб-чата."""
    redis = get_redis()
    if redis.enabled:
        return jsonify({
            "active_sessions": "redis (см. Redis CLI)",
            "status": "ok",
            "storage": "redis",
        })
    return jsonify({
        "active_sessions": len(WEB_SESSIONS),
        "status": "ok",
        "storage": "memory",
    })