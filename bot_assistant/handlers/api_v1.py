"""
API v1 — версионированные эндпоинты.
Все новые клиенты должны использовать /api/v1/...
"""

from flask import Blueprint, jsonify, request

from bot_assistant.logger import get_logger
from bot_assistant.models import Lead
from bot_assistant.redis_client import get_redis
from bot_assistant.security import check_origin
from bot_assistant.services import get_lead_repository, get_notifier
from bot_assistant.validators import (
    normalize_phone,
    validate_lead_data,
    ValidationError,
)

logger = get_logger(__name__)

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


@api_v1_bp.route("/health", methods=["GET"])
def health():
    """Health check."""
    return jsonify({
        "status": "ok",
        "version": "2.0.0",
        "api_version": "v1",
        "service": "AutoMaster+ Assistant",
    })


@api_v1_bp.route("/leads", methods=["POST"])
def create_lead():
    """
    Создаёт новую заявку.

    POST /api/v1/leads
    {
        "name": "Иван",
        "phone": "+79991234567",
        "car": "Toyota",
        "service": "Ремонт",
        "desired_datetime": "2026-12-25 14:00",
        "comment": "опционально",
        "source": "api"
    }
    """
    # Проверка Origin для CSRF-защиты API
    is_valid, error_msg = check_origin()
    if not is_valid:
        logger.warning("API v1: Origin check failed: %s", error_msg)
        return jsonify({"error": error_msg}), 403

    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"error": "invalid JSON"}), 400

    # Валидация обязательных полей
    required_fields = ["name", "phone", "car", "service", "desired_datetime"]
    missing = [f for f in required_fields if not payload.get(f)]
    if missing:
        return jsonify({
            "error": f"Missing required fields: {', '.join(missing)}",
            "missing_fields": missing,
        }), 400

    try:
        validate_lead_data(payload)
    except ValidationError as e:
        return jsonify({"error": str(e), "field": e.field}), 400

    # Нормализация телефона
    phone = payload.get("phone", "")
    if phone:
        phone = normalize_phone(phone)

    lead = Lead(
        source=payload.get("source", "api"),
        name=payload.get("name", ""),
        phone=phone,
        car=payload.get("car", ""),
        service=payload.get("service", ""),
        desired_datetime=payload.get("desired_datetime", ""),
        comment=payload.get("comment", ""),
        user_id=payload.get("user_id", ""),
    )

    try:
        repo = get_lead_repository()
        saved_lead = repo.add(lead)

        # Отправляем уведомление (не блокируем ответ)
        try:
            notifier = get_notifier()
            notifier.notify_lead(lead)
        except Exception as e:
            logger.warning("API v1: notification failed: %s", e)

        return jsonify({
            "status": "created",
            "lead": saved_lead.to_dict(),
        }), 201

    except Exception as e:
        logger.exception("API v1: failed to create lead: %s", e)
        return jsonify({"error": "Failed to save lead"}), 500


@api_v1_bp.route("/leads", methods=["GET"])
def list_leads():
    """
    Возвращает список заявок.

    GET /api/v1/leads?limit=50&offset=0
    """
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    # Ограничения
    limit = min(limit, 1000)
    offset = max(offset, 0)

    try:
        repo = get_lead_repository()
        leads = repo.get_all(limit=limit, offset=offset)
        total = repo.count()

        return jsonify({
            "leads": [lead.to_dict() for lead in leads],
            "total": total,
            "limit": limit,
            "offset": offset,
        })

    except Exception as e:
        logger.exception("API v1: failed to list leads: %s", e)
        return jsonify({"error": "Failed to fetch leads"}), 500


@api_v1_bp.route("/leads/<int:lead_id>", methods=["GET"])
def get_lead(lead_id: int):
    """Возвращает заявку по ID."""
    try:
        repo = get_lead_repository()
        lead = repo.get_by_id(lead_id)

        if lead is None:
            return jsonify({"error": "Lead not found"}), 404

        return jsonify({"lead": lead.to_dict()})

    except Exception as e:
        logger.exception("API v1: failed to get lead %d: %s", lead_id, e)
        return jsonify({"error": "Failed to fetch lead"}), 500


@api_v1_bp.route("/leads/<int:lead_id>/status", methods=["PATCH"])
def update_lead_status(lead_id: int):
    """
    Обновляет статус заявки.

    PATCH /api/v1/leads/1/status
    {"status": "contacted"}
    """
    # Проверка Origin для CSRF-защиты API
    is_valid, error_msg = check_origin()
    if not is_valid:
        logger.warning("API v1: Origin check failed: %s", error_msg)
        return jsonify({"error": error_msg}), 403

    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"error": "invalid JSON"}), 400

    new_status = payload.get("status", "").strip()
    valid_statuses = {"new", "contacted", "completed", "cancelled"}

    if new_status not in valid_statuses:
        return jsonify({
            "error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        }), 400

    try:
        repo = get_lead_repository()
        success = repo.update_status(lead_id, new_status)

        if not success:
            return jsonify({"error": "Lead not found or status update not supported"}), 404

        return jsonify({"status": "updated", "lead_id": lead_id, "new_status": new_status})

    except Exception as e:
        logger.exception("API v1: failed to update lead status: %s", e)
        return jsonify({"error": "Failed to update status"}), 500


@api_v1_bp.route("/stats", methods=["GET"])
def stats():
    """Возвращает статистику."""
    try:
        repo = get_lead_repository()
        total = repo.count()
        leads = repo.get_all(limit=1000)

        new_count = sum(1 for l in leads if l.status == "new")
        contacted_count = sum(1 for l in leads if l.status == "contacted")
        completed_count = sum(1 for l in leads if l.status == "completed")

        return jsonify({
            "total": total,
            "by_status": {
                "new": new_count,
                "contacted": contacted_count,
                "completed": completed_count,
            },
        })

    except Exception as e:
        logger.exception("API v1: stats failed: %s", e)
        return jsonify({"error": "Failed to get stats"}), 500