"""
AutoMaster+ Assistant — точка входа в приложение.

Запуск:
    python main.py              # Flask + Telegram бот
    python main.py --flask-only # Только Flask сервер
    python main.py --bot-only   # Только Telegram бот
"""

import argparse
import logging
import os
import signal
import sys
import threading
from typing import Optional

from flask import Flask, jsonify

from bot_assistant.config import load_config
from bot_assistant.di import Container, get_container
from bot_assistant.handlers import (
    get_admin_bp,
    get_api_v1_bp,
    get_docs_bp,
    get_webchat_bp,
)
from bot_assistant.logger import setup_logger
from bot_assistant.middleware import (
    CorrelationMiddleware,
    RequestLoggingMiddleware,
    register_error_handlers,
)

logger = logging.getLogger(__name__)

# Глобальные ссылки для graceful shutdown
_bot_thread: Optional[threading.Thread] = None
_container: Optional[Container] = None


def create_flask_app() -> Flask:
    """
    Создаёт и настраивает Flask приложение.

    Returns:
        Настроенный Flask app
    """
    global _container

    # Инициализируем DI контейнер
    _container = get_container()
    _container.initialize()

    config = _container.config

    # Создаём Flask приложение
    app = Flask(
        __name__,
        template_folder=os.path.join(
            os.path.dirname(__file__), "bot_assistant", "templates"
        ),
    )
    app.secret_key = config.flask.secret_key or "dev-secret-key"

    # Middleware (WSGI-level)
    app.wsgi_app = CorrelationMiddleware(app.wsgi_app)
    app.wsgi_app = RequestLoggingMiddleware(app.wsgi_app)

    # Регистрируем Blueprint'ы
    app.register_blueprint(get_webchat_bp())
    app.register_blueprint(get_admin_bp())
    app.register_blueprint(get_api_v1_bp())
    app.register_blueprint(get_docs_bp())

    # Регистрируем обработчики ошибок
    register_error_handlers(app)

    # Корневой эндпоинт
    @app.route("/")
    def index():
        return jsonify({
            "service": "AutoMaster+ Assistant",
            "version": "2.0.0",
            "docs": "/docs",
            "health": "/health",
        })

    @app.route("/health")
    def health():
        return jsonify({
            "status": "ok",
            "version": "2.0.0",
            "service": "AutoMaster+ Assistant",
        })

    # Инициализируем БД (создаём таблицы, если их нет)
    if config.database.enabled and _container.database:
        _container.database.init_db()

    logger.info("Flask app created successfully")
    return app


def run_flask(
    app: Flask, host: str = "0.0.0.0", port: int = 8000, debug: bool = False
):
    """Запускает Flask сервер."""
    logger.info("Starting Flask server on %s:%s (debug=%s)", host, port, debug)
    app.run(host=host, port=port, debug=debug, use_reloader=False)


def run_telegram_bot():
    """Запускает Telegram бота в отдельном потоке."""
    import asyncio

    # Создаём новый event loop для этого потока
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    from bot_assistant.handlers.telegram_bot import build_application

    config = get_container().config

    if not config.telegram.bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN не настроен — Telegram бот не запущен")
        return

    logger.info("Starting Telegram bot (mode: %s)", config.telegram.mode)
    application = build_application()

    if config.telegram.mode == "webhook" and config.telegram.webhook_url:
        # Webhook mode
        application.run_webhook(
            listen="0.0.0.0",
            port=config.flask.port,
            url_path=config.telegram.bot_token,
            webhook_url=(
                f"{config.telegram.webhook_url}/{config.telegram.bot_token}"
            ),
        )
    else:
        # Polling mode (по умолчанию)
        application.run_polling(allowed_updates=None)


def graceful_shutdown(signum, frame):
    """Обработчик graceful shutdown."""
    global _bot_thread, _container

    logger.info("Received signal %s, shutting down gracefully...", signum)

    # Останавливаем DI контейнер
    if _container:
        _container.shutdown()

    # Останавливаем thread pool
    from bot_assistant.async_utils import shutdown_executor

    shutdown_executor()

    logger.info("Shutdown complete")
    sys.exit(0)


def main():
    """Главная функция запуска."""
    global _bot_thread

    parser = argparse.ArgumentParser(description="AutoMaster+ Assistant")
    parser.add_argument(
        "--flask-only",
        action="store_true",
        help="Запустить только Flask сервер",
    )
    parser.add_argument(
        "--bot-only",
        action="store_true",
        help="Запустить только Telegram бота",
    )
    parser.add_argument(
        "--host", type=str, default=None, help="Хост для Flask сервера"
    )
    parser.add_argument(
        "--port", type=int, default=None, help="Порт для Flask сервера"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Режим отладки"
    )
    args = parser.parse_args()

    # Настраиваем логирование
    setup_logger(level="INFO")

    # Регистрируем обработчики сигналов для graceful shutdown
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    # Создаём Flask приложение
    app = create_flask_app()
    config = get_container().config

    host = args.host or config.flask.host
    port = args.port or config.flask.port
    debug = args.debug or config.flask.debug

    if args.bot_only:
        # Только Telegram бот
        run_telegram_bot()
    elif args.flask_only:
        # Только Flask сервер
        run_flask(app, host=host, port=port, debug=debug)
    else:
        # Flask + Telegram бот
        _bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
        _bot_thread.start()
        run_flask(app, host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()