from telegram import Update
from telegram.ext import ContextTypes
from bot.handlers.calendar import today, week, add_calendar_start
from bot.handlers.upcoming import upcoming_zoom
from bot.handlers.notifications import notification_settings
from bot.handlers.help import help_command
from bot.database import async_session, User
from bot.services.logger import send_log
import logging

logger = logging.getLogger(__name__)

async def check_access(user_id):
    async with async_session() as session:
        user = await session.get(User, user_id)
        return user and user.is_approved and not user.is_blocked

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    
    logger.info(f"Menu handler: user {user.id}, text: {text}")

    await send_log(f"👤 {user.first_name} (@{user.username}, ID: {user.id}): {text}")

    if not await check_access(user.id):
        await update.message.reply_text("⛔ Нет доступа. Ожидайте подтверждения.")
        return

    # Обработка кнопок с точным соответствием
    if text == "📅 Сегодня":
        await today(update, context)
    elif text == "📆 Неделя":
        await week(update, context)
    elif text == "🔔 Уведомления":
        await notification_settings(update, context)
    elif text == "🎥 Zoom календарь":
        await upcoming_zoom(update, context)
    elif text == "➕ Zoom" or text == "➕ Zoom встреча":
        from bot.handlers.zoom import create_meeting_start
        await create_meeting_start(update, context)
    elif text == "➕ Встреча":
        from bot.handlers.create_event import create_event_start
        await create_event_start(update, context)
    elif text == "📋 Календарь" or text == "📋 Добавить свой календарь":
        await add_calendar_start(update, context)
    elif text == "ℹ️ Помощь":
        await help_command(update, context)
    elif text == "👥 Пользователи":
        from bot.handlers.admin import list_users
        await list_users(update, context)
    else:
        # Если текст не совпадает с кнопками, возможно это команда
        await update.message.reply_text(
            "Используйте кнопки меню или команды.\n"
            "/help — помощь\n\n"
            "📋 <b>Доступные команды:</b>\n"
            "/today — встречи на сегодня\n"
            "/week — встречи на неделю\n"
            "/create_event — создать встречу\n"
            "/create_zoom — создать Zoom встречу\n"
            "/addcalendar — добавить календарь\n"
            "/notifications — уведомления",
            parse_mode="HTML",
            disable_web_page_preview=True
        )