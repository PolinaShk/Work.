import logging
import sys
from pathlib import Path

log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, CallbackQueryHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
from bot.config import BOT_TOKEN, ADMIN_CHAT_ID, LOGS_CHAT_ID, PROXY_URL
from bot.database import init_db
from bot.handlers.admin import start, approve_user, block_user, unblock_user, list_users, button_handler
from bot.handlers.calendar import today, week, add_calendar_start, get_email, get_password, cancel as calendar_cancel, EMAIL, PASSWORD
from bot.handlers.notifications import notification_settings, toggle_daily, toggle_weekly
from bot.handlers.zoom import create_meeting_start, meeting_summary, meeting_start_time, meeting_duration, meeting_location, meeting_attendees, cancel as zoom_cancel, force_create_zoom_handler, find_free_time_zoom_handler, find_free_time_zoom_confirm_handler, FORCE_CREATE_ZOOM, FIND_FREE_TIME_ZOOM, SUMMARY, START_TIME, DURATION, LOCATION, ATTENDEES
from bot.handlers.create_event import create_event_start, event_summary, event_start_time, event_duration, event_location, event_attendees, cancel as event_cancel, force_create_handler, find_free_time_handler, find_free_time_confirm_handler, EVT_SUMMARY, EVT_START, EVT_DURATION, EVT_LOCATION, EVT_ATTENDEES, FORCE_CREATE, FIND_FREE_TIME
from bot.handlers.help import help_command
from bot.handlers.menu import menu_handler
from bot.handlers.upcoming import upcoming_zoom
from bot.services.notifications import send_notifications
from bot.services.logger import send_log
from bot.services.proxy_handler import retry_last_action_handler, main_menu_handler


async def error_handler(update, context):
    error_msg = str(context.error)
    logger.error(f"Error: {error_msg}", exc_info=True)
    await send_log(f"❌ Ошибка: {error_msg}")
    
    if update and update.effective_user and update.effective_chat:
        error_lower = error_msg.lower()
        proxy_keywords = ['proxy', 'connection', 'timeout', 'network', 'remote', 'ssl', 'certificate']
        
        if any(keyword in error_lower for keyword in proxy_keywords):
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="🔌 <b>Проблема с подключением к серверу</b>\n\n"
                         "Возможно, проблема с прокси-сервером или интернет-соединением.\n"
                         "📌 <b>Что делать:</b>\n"
                         "• Подождите 1-2 минуты и повторите действие\n"
                         "• Используйте команду /start для перезапуска\n"
                         "• Если проблема повторяется, обратитесь к администратору",
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"Не удалось отправить сообщение пользователю: {e}")


async def post_init(application):
    await init_db()
    application.bot_data["admin_chat_id"] = ADMIN_CHAT_ID

    scheduler = AsyncIOScheduler(timezone=pytz.timezone("Europe/Moscow"))
    scheduler.add_job(send_notifications, "cron", minute="*", args=[application])
    scheduler.start()
    logger.info("Scheduler started")
    
    startup_message = "✅ Бот iCalendarPM запущен и готов к работе"
    await send_log(startup_message)
    
    if ADMIN_CHAT_ID:
        try:
            await application.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=startup_message,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение админу: {e}")


def main():
    builder = Application.builder().token(BOT_TOKEN).post_init(post_init)
    if PROXY_URL:
        builder = builder.proxy(PROXY_URL).get_updates_proxy(PROXY_URL)
    app = builder.build()

    # Базовые команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve", approve_user))
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("unblock", unblock_user))
    app.add_handler(CommandHandler("users", list_users))
    app.add_handler(CommandHandler("help", help_command))

    # Кнопки подтверждения/отклонения
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(approve_|block_)"))

    # Мгновенные команды
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(CommandHandler("zoom_upcoming", upcoming_zoom))

    # Добавление календаря
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("addcalendar", add_calendar_start),
            MessageHandler(filters.Regex("^📋 Добавить свой календарь$"), add_calendar_start),
        ],
        states={
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
        },
        fallbacks=[CommandHandler("cancel", calendar_cancel)]
    ))

    # Уведомления
    app.add_handler(CommandHandler("notifications", notification_settings))
    app.add_handler(CallbackQueryHandler(toggle_daily, pattern="^toggle_daily$"))
    app.add_handler(CallbackQueryHandler(toggle_weekly, pattern="^toggle_weekly$"))

    # Создание встречи
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("create_event", create_event_start),
            MessageHandler(filters.Regex("^➕ Встреча$"), create_event_start),
        ],
        states={
            EVT_SUMMARY: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_summary)],
            EVT_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_start_time)],
            EVT_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_duration)],
            EVT_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_location)],
            EVT_ATTENDEES: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_attendees)],
            FORCE_CREATE: [CallbackQueryHandler(force_create_handler, pattern="^(force_create|cancel_create|find_free_time)$")],
            FIND_FREE_TIME: [CallbackQueryHandler(find_free_time_confirm_handler, pattern="^(free_slot_|cancel_find_free_time)")],
        },
        fallbacks=[CommandHandler("cancel", event_cancel)]
    ))

    # Zoom
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("create_zoom", create_meeting_start),
            MessageHandler(filters.Regex("^➕ Zoom встреча$"), create_meeting_start),
        ],
        states={
            SUMMARY: [MessageHandler(filters.TEXT & ~filters.COMMAND, meeting_summary)],
            START_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, meeting_start_time)],
            DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, meeting_duration)],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, meeting_location)],
            ATTENDEES: [MessageHandler(filters.TEXT & ~filters.COMMAND, meeting_attendees)],
            FORCE_CREATE_ZOOM: [CallbackQueryHandler(force_create_zoom_handler, pattern="^(force_create_zoom|cancel_create_zoom|find_free_time_zoom)$")],
            FIND_FREE_TIME_ZOOM: [CallbackQueryHandler(find_free_time_zoom_confirm_handler, pattern="^(find_free_time_zoom_confirm|cancel_find_free_time_zoom)")],
        },
        fallbacks=[CommandHandler("cancel", zoom_cancel)]
    ))

    # Остальные кнопки меню
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))
    
    # Обработчики ошибок прокси
    app.add_handler(CallbackQueryHandler(retry_last_action_handler, pattern="^retry_last_action$"))
    app.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^main_menu$"))

    app.add_error_handler(error_handler)

    logger.info("iCalendarPM started")
    app.run_polling()


if __name__ == "__main__":
    main()