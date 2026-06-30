from telegram import Update
from telegram.ext import ContextTypes

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """<b>📋 Доступные команды:</b>

<b>📅 Календарь:</b>
/addcalendar — добавить CalDAV календарь
/today — встречи на сегодня
/week — встречи на неделю
/create_event — создать встречу в календаре

<b>🎥 Zoom:</b>
/create_zoom — создать Zoom-встречу
/zoom_upcoming — 10 ближайших Zoom встреч

<b>🔔 Уведомления:</b>
/notifications — настройки уведомлений

<b>👑 Администрирование:</b>
/users — список пользователей
/approve ID — подтвердить
/block ID — заблокировать
/unblock ID — разблокировать

<b>ℹ️ Другое:</b>
/start — перезапуск бота
/help — это сообщение
/cancel — отмена

<b>🔘 Кнопки меню:</b>
• 📅 Сегодня — встречи на сегодня
• 📆 Неделя — встречи на неделю
• ➕ Встреча — создать обычную встречу
• ➕ Zoom встреча — создать Zoom встречу
• 🔔 Уведомления — настройки уведомлений
• 📋 Добавить свой календарь — добавить CalDAV календарь
• 🎥 Календарь zoom — показать 10 ближайших Zoom встреч
• 👥 Пользователи — список пользователей (админ)
"""
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)