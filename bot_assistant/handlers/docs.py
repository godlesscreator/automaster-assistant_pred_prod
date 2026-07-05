"""
Blueprint для документации API.
Предоставляет:
- /openapi.yaml — OpenAPI 3.0.3 спецификация
- /docs — Swagger UI для интерактивной документации
"""

import os
from pathlib import Path

from flask import Blueprint, jsonify, send_file

from bot_assistant.logger import get_logger

logger = get_logger(__name__)

docs_bp = Blueprint("docs", __name__, url_prefix="")

# Путь к файлу openapi.yaml относительно корня проекта
_OPENAPI_PATH = Path(__file__).resolve().parent.parent.parent / "openapi.yaml"


@docs_bp.route("/openapi.yaml")
def openapi_spec():
    """Возвращает OpenAPI 3.0.3 спецификацию."""
    if not _OPENAPI_PATH.exists():
        logger.error("openapi.yaml not found at %s", _OPENAPI_PATH)
        return jsonify({"error": "OpenAPI spec not found"}), 404
    return send_file(str(_OPENAPI_PATH), mimetype="text/yaml")


@docs_bp.route("/docs")
def swagger_ui():
    """Возвращает Swagger UI страницу."""
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoMaster+ Assistant API — Swagger UI</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <style>
        html {{ box-sizing: border-box; overflow-y: scroll; }}
        *, *:before, *:after {{ box-sizing: inherit; }}
        body {{ margin: 0; background: #fafafa; }}
        .topbar {{ display: none; }}
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        SwaggerUIBundle({{
            url: '/openapi.yaml',
            dom_id: '#swagger-ui',
            deepLinking: true,
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.SwaggerUIStandalonePreset,
            ],
            layout: "BaseLayout",
            defaultModelsExpandDepth: 1,
            defaultModelExpandDepth: 1,
            docExpansion: "list",
        }});
    </script>
</body>
</html>"""
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


__all__ = ["docs_bp"]