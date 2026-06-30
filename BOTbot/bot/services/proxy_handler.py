import logging
from functools import wraps
from telegram.error import NetworkError, TimedOut, RetryAfter
import asyncio

logger = logging.getLogger(__name__)

class ProxyErrorHandler:
    def __init__(self):
        self.retry_count = {}
        self.max_retries = 3
        self.retry_delay = 2

    async def handle_error(self, update, context, error, original_callback=None, original_args=None):
        user_id = update.effective_user.id if update.effective_user else None
        chat_id = update.effective_chat.id if update.effective_chat else None
        error_str = str(error).lower()

        if "proxy" in error_str:
            error_type = "proxy"
            message = "🔌 <b>Ошибка подключения к прокси-серверу</b>\n\n"
            message += "Прокси-сервер временно недоступен.\n\n"
            message += "📌 <b>Рекомендации:</b>\n"
            message += "• Подождите 30 секунд и повторите действие\n"
            message += "• Используйте кнопку «Повторить» ниже\n"
            message += "• Если ошибка повторяется, сообщите администратору"
        elif "timeout" in error_str:
            error_type = "timeout"
            message = "⏰ <b>Превышено время ожидания</b>\n\n"
            message += "Сервер отвечает слишком долго.\n\n"
            message += "📌 <b>Рекомендации:</b>\n"
            message += "• Проверьте интернет-соединение\n"
            message += "• Повторите действие через минуту"
        elif "connection" in error_str:
            error_type = "connection"
            message = "🔌 <b>Проблема с подключением</b>\n\n"
            message += "Не удалось установить соединение с сервером.\n\n"
            message += "📌 <b>Рекомендации:</b>\n"
            message += "• Проверьте стабильность интернета\n"
            message += "• Повторите действие через минуту"
        elif "401" in error_str or "unauthorized" in error_str:
            error_type = "auth"
            message = "🔑 <b>Ошибка авторизации календаря</b>\n\n"
            message += "Ваш пароль календаря неверен или истёк срок действия.\n\n"
            message += "📌 <b>Решение:</b>\n"
            message += "Используйте команду /addcalendar, чтобы добавить календарь заново"
        else:
            error_type = "unknown"
            message = f"⚠️ <b>Произошла ошибка</b>\n\n"
            message += f"<code>{str(error)[:200]}</code>\n\n"
            message += "Пожалуйста, попробуйте позже или обратитесь к администратору."

        logger.error(f"Ошибка для пользователя {user_id}: {error_type} - {error}")

        from telegram import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = None
        if error_type in ["proxy", "timeout", "connection"]:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Повторить действие", callback_data="retry_last_action")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ])

        try:
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(
                    message,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
            elif update and update.message:
                await update.message.reply_text(
                    message,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
            elif chat_id and context and context.bot:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
            else:
                logger.warning(f"Не удалось отправить сообщение об ошибке")
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке: {e}")

        if original_callback and original_args:
            context.user_data["retry_callback"] = original_callback
            context.user_data["retry_args"] = original_args
            context.user_data["retry_chat_id"] = chat_id

        return error_type

    def can_retry(self, user_id):
        if user_id not in self.retry_count:
            self.retry_count[user_id] = 0
            return True
        if self.retry_count[user_id] < self.max_retries:
            self.retry_count[user_id] += 1
            return True
        return False

    def reset_retry(self, user_id):
        if user_id in self.retry_count:
            del self.retry_count[user_id]

proxy_handler = ProxyErrorHandler()

def handle_proxy_errors(original_func=None, *, retry_on_error=True):
    def decorator(func):
        @wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            user_id = update.effective_user.id if update.effective_user else None
            try:
                return await func(update, context, *args, **kwargs)
            except (NetworkError, TimedOut, RetryAfter) as e:
                logger.error(f"Network error in {func.__name__}: {e}")
                if retry_on_error and proxy_handler.can_retry(user_id):
                    await asyncio.sleep(proxy_handler.retry_delay)
                    try:
                        return await func(update, context, *args, **kwargs)
                    except Exception as retry_error:
                        await proxy_handler.handle_error(
                            update, context, retry_error,
                            original_callback=func,
                            original_args=(update, context) + args
                        )
                else:
                    await proxy_handler.handle_error(update, context, e, func, (update, context) + args)
                return None
            except Exception as e:
                await proxy_handler.handle_error(update, context, e)
                return None
        return wrapper
    if original_func:
        return decorator(original_func)
    return decorator

async def retry_last_action_handler(update, context):
    query = update.callback_query
    await query.answer()

    retry_callback = context.user_data.get("retry_callback")
    retry_args = context.user_data.get("retry_args")

    if retry_callback and retry_args:
        await query.edit_message_text("🔄 Повторяю действие...", disable_web_page_preview=True)
        user_id = update.effective_user.id
        proxy_handler.reset_retry(user_id)
        try:
            if retry_args and len(retry_args) >= 2:
                await retry_callback(retry_args[0], retry_args[1])
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка при повторе: {str(e)[:200]}", disable_web_page_preview=True)
    else:
        await query.edit_message_text("❌ Нет действия для повторения. Пожалуйста, начните заново.", disable_web_page_preview=True)
    return True

async def main_menu_handler(update, context):
    query = update.callback_query
    await query.answer()
    
    # Создаем клавиатуру прямо здесь, чтобы избежать проблем с импортом
    from telegram import ReplyKeyboardMarkup
    main_keyboard = ReplyKeyboardMarkup([
        ["📅 Сегодня", "📆 Неделя"],
        ["➕ Встреча", "➕ Zoom встреча"],
        ["🔔 Уведомления", "📋 Добавить свой календарь"],
        ["🎥 Zoom календарь", "ℹ️ Помощь"],
        ["👥 Пользователи"]
    ], resize_keyboard=True)
    
    await query.edit_message_text(
        "🏠 <b>Главное меню</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=main_keyboard
    )
    return True