"""
Обработчики админ-панели (Flask Dashboard).
"""

import functools
from datetime import datetime

from flask import (
    Blueprint, jsonify, render_template, request, Response, session,
)

from bot_assistant.config import get_config
from bot_assistant.logger import get_logger
from bot_assistant.security import (
    check_login_rate_limit,
    record_failed_login,
    record_successful_login,
)

logger = get_logger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _get_client_ip() -> str:
    """Возвращает IP адрес клиента с учётом прокси."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _check_admin_auth() -> bool:
    """
    Проверяет базовую HTTP-аутентификацию для админ-панели.
    С защитой от brute-force атак.
    """
    config = get_config()
    if not config.admin.enabled:
        return False
    if not config.admin.password:
        # Если пароль не установлен — пускаем всех, но логируем предупреждение
        logger.warning("ADMIN_PASSWORD не установлен! Админ-панель без пароля.")
        return True

    auth = request.authorization
    if not auth:
        return False

    ip_address = _get_client_ip()

    # Проверяем rate limit перед проверкой пароля
    allowed, error_msg = check_login_rate_limit(
        username=auth.username,
        ip_address=ip_address,
    )
    if not allowed:
        logger.warning(
            "Login blocked for user '%s' from IP %s (rate limit)",
            auth.username, ip_address,
        )
        return False

    # Проверяем пароль
    is_valid = (
        auth.username == config.admin.username
        and auth.password == config.admin.password
    )

    if is_valid:
        record_successful_login(auth.username, ip_address)
    else:
        record_failed_login(auth.username, ip_address)

    return is_valid


def admin_required(f):
    """Декоратор, требующий аутентификации для доступа к админ-панели."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not _check_admin_auth():
            return Response(
                "Требуется аутентификация",
                401,
                {"WWW-Authenticate": 'Basic realm="AutoMaster+ Admin"'},
            )
        return f(*args, **kwargs)
    return decorated


@admin_bp.route("/")
@admin_required
def admin_dashboard():
    """Главная страница админ-панели."""
    try:
        from bot_assistant.services import get_lead_repository
        repo = get_lead_repository()
        leads = repo.get_all(limit=50)
    except Exception as e:
        logger.exception("Admin: failed to get leads: %s", e)
        leads = []

    today = datetime.now().strftime("%Y-%m-%d")
    stats = {
        "total": len(leads),
        "new": len([l for l in leads if l.status == "new"]),
        "today": len([l for l in leads if l.timestamp and l.timestamp.startswith(today)]),
        "active_sessions": 0,
    }

    return render_template("admin.html", stats=stats, leads=leads)


@admin_bp.route("/leads")
@admin_required
def admin_leads():
    """Страница со списком заявок (JSON)."""
    try:
        from bot_assistant.services import get_lead_repository
        repo = get_lead_repository()
        leads = repo.get_all(limit=100)
        return jsonify([lead.to_dict() for lead in leads])
    except Exception as e:
        logger.exception("Admin: failed to get leads: %s", e)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/export")
@admin_required
def admin_export():
    """Экспорт заявок в CSV."""
    try:
        from bot_assistant.services import get_lead_repository
        repo = get_lead_repository()
        leads = repo.get_all(limit=1000)
    except Exception as e:
        logger.exception("Admin: export failed: %s", e)
        return jsonify({"error": str(e)}), 500

    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Дата", "Источник", "Имя", "Телефон", "Авто",
        "Услуга", "Желаемая дата", "Комментарий", "Статус"
    ])

    for lead in leads:
        writer.writerow([
            lead.timestamp,
            lead.source,
            lead.name,
            lead.phone,
            lead.car,
            lead.service,
            lead.desired_datetime,
            lead.comment,
            lead.status,
        ])

    csv_content = output.getvalue()
    output.close()

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=leads_export.csv"},
    )