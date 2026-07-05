"""
Обработчики Telegram бота.
"""

from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from bot_assistant.async_utils import run_sync
from bot_assistant.config import get_config
from bot_assistant.logger import get_logger
from bot_assistant.models import Lead
from bot_assistant.services import get_lead_repository, get_notifier
from bot_assistant.validators import (
    validate_name,
    validate_phone,
    validate_car,
    validate_service,
    validate_datetime,
    validate_comment,
    ValidationError,
)

logger = get_logger(__name__)

# Состояния для ConversationHandler
NAME, PHONE, CAR, SERVICE, DESIRED_DT, COMMENT = range(6)

# Промпты для каждого шага
PROMPTS = {
    "name": "Как вас зовут?",
    "phone": "Ваш номер телефона?",
    "car": "Марка и модель автомобиля?",
    "service": "Какая услуга нужна? (ТО, ремонт, диагностика, покраска и др.)",
    "desired_datetime": "Желаемая дата/время визита? (например: 2025-03-15 14:00)",
    "comment": "Добавите комментарий? Если нет — напишите: нет",
}


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start."""
    user = update.effective_user
    logger.info("Telegram: /start from user %s (%s)", user.id, user.full_name)

    await update.message.reply_text(
        f"Здравствуйте, {user.first_name or 'клиент'}! 👋\n\n"
        "Я — ассистент автосервиса. Помогу оформить заявку на ремонт или обслуживание.\n\n"
        "Давайте начнём. Как вас зовут?"
    )
    context.user_data.clear()
    return NAME


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /cancel."""
    user = update.effective_user
    logger.info("Telegram: /cancel from user %s", user.id)
    await update.message.reply_text(
        "❌ Отменено. Если понадобится помощь — напишите /start."
    )
    return ConversationHandler.END


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /help."""
    await update.message.reply_text(
        "🔧 <b>Доступные команды:</b>\n\n"
        "/start — Оформить новую заявку\n"
        "/status — Проверить статус заявки\n"
        "/help — Показать эту справку\n"
        "/cancel — Отменить текущий диалог\n\n"
        "Просто напишите вопрос — я проконсультирую вас по услугам.",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /status."""
    await update.message.reply_text(
        "Ваша заявка обрабатывается. Мы свяжемся с вами в ближайшее время.\n"
        "Если у вас срочный вопрос — позвоните нам."
    )
    return ConversationHandler.END


async def collect_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сбор имени."""
    text = (update.message.text or "").strip()
    try:
        name = validate_name(text)
        context.user_data["name"] = name
        logger.debug("Telegram: name collected: %s", name)
        await update.message.reply_text(f"Приятно познакомиться, {name}! 📞\n\nТеперь укажите ваш номер телефона:")
        return PHONE
    except ValidationError as e:
        await update.message.reply_text(f"❌ {e.message}\n\nПожалуйста, введите имя заново:")
        return NAME


async def collect_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сбор телефона."""
    text = (update.message.text or "").strip()
    try:
        phone = validate_phone(text)
        context.user_data["phone"] = phone
        logger.debug("Telegram: phone collected: %s", phone)
        await update.message.reply_text("Отлично! 🚗\n\nТеперь укажите марку и модель автомобиля:")
        return CAR
    except ValidationError as e:
        await update.message.reply_text(f"❌ {e.message}\n\nПример: +7 999 123-45-67")
        return PHONE


async def collect_car(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сбор автомобиля."""
    text = (update.message.text or "").strip()
    try:
        car = validate_car(text)
        context.user_data["car"] = car
        logger.debug("Telegram: car collected: %s", car)
        await update.message.reply_text("Понял! 🔧\n\nКакая услуга нужна? (ТО, ремонт, диагностика, покраска и др.)")
        return SERVICE
    except ValidationError as e:
        await update.message.reply_text(f"❌ {e.message}")
        return CAR


async def collect_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сбор услуги."""
    text = (update.message.text or "").strip()
    try:
        service = validate_service(text)
        context.user_data["service"] = service
        logger.debug("Telegram: service collected: %s", service)
        await update.message.reply_text("Хорошо! 📅\n\nЖелаемая дата и время визита?\n(например: 2025-03-15 14:00)")
        return DESIRED_DT
    except ValidationError as e:
        await update.message.reply_text(f"❌ {e.message}")
        return SERVICE


async def collect_dt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сбор даты/времени."""
    text = (update.message.text or "").strip()
    try:
        dt = validate_datetime(text)
        context.user_data["desired_datetime"] = dt
        logger.debug("Telegram: datetime collected: %s", dt)
        await update.message.reply_text("Почти готово! 💬\n\nДобавите комментарий? Если нет — напишите: нет")
        return COMMENT
    except ValidationError as e:
        await update.message.reply_text(f"❌ {e.message}\n\nПример: 2025-03-15 14:00")
        return DESIRED_DT


async def collect_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сбор комментария и сохранение заявки."""
    text = (update.message.text or "").strip()
    try:
        comment = validate_comment(text)
    except ValidationError as e:
        await update.message.reply_text(f"❌ {e.message}")
        return COMMENT

    context.user_data["comment"] = comment

    # Формируем заявку
    lead = Lead(
        source="telegram",
        name=context.user_data.get("name", ""),
        phone=context.user_data.get("phone", ""),
        car=context.user_data.get("car", ""),
        service=context.user_data.get("service", ""),
        desired_datetime=context.user_data.get("desired_datetime", ""),
        comment=comment,
        user_id=str(update.effective_user.id if update.effective_user else ""),
    )

    # Сохраняем (асинхронно, не блокируем event loop)
    try:
        repo = get_lead_repository()
        await run_sync(repo.add, lead)

        notifier = get_notifier()
        await run_sync(notifier.notify_lead, lead)

        await update.message.reply_text(
            "✅ <b>Спасибо! Ваша заявка принята!</b>\n\n"
            "Мы свяжемся с вами в ближайшее время для подтверждения.\n"
            "Если понадобится ещё что-то — напишите /start.",
            parse_mode="HTML",
        )
        logger.info("Telegram: lead saved for user %s", lead.user_id)

    except Exception as e:
        logger.exception("Telegram: failed to save lead: %s", e)
        await update.message.reply_text(
            "❌ Произошла ошибка при сохранении заявки.\n"
            "Пожалуйста, попробуйте позже или позвоните нам."
        )

    return ConversationHandler.END


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик свободных сообщений (консультация через OpenAI)."""
    text = (update.message.text or "").strip()
    if not text:
        return

    logger.info("Telegram: free message from %s: %s...", update.effective_user.id, text[:50])

    try:
        from bot_assistant.services.openai_service import get_openai_service
        openai = get_openai_service()
        # Асинхронный вызов — не блокируем event loop
        response = await run_sync(
            openai.ask,
            prompt=text,
            system="Ты — консультант автосервиса. Отвечай кратко и по делу. "
                   "Если вопрос про запись — предложи написать /start.",
        )
        await update.message.reply_text(response)
    except Exception as e:
        logger.error("Telegram: OpenAI error: %s", e)
        await update.message.reply_text(
            "Извините, временно не могу ответить на вопрос. "
            "Попробуйте оформить заявку через /start."
        )


def build_application() -> Optional[Application]:
    """Создаёт и настраивает Telegram приложение."""
    config = get_config()
    token = config.telegram.bot_token

    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set; bot disabled")
        return None

    app = ApplicationBuilder().token(token).build()

    # ConversationHandler для сбора заявок
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_phone)],
            CAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_car)],
            SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_service)],
            DESIRED_DT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_dt)],
            COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_comment)],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CommandHandler("help", cmd_help),
            CommandHandler("status", cmd_status),
        ],
    )

    app.add_handler(conv_handler)

    # Обработчик свободных сообщений (не в диалоге)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Telegram bot application built successfully")
    return app