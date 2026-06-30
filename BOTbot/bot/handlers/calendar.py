from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from datetime import datetime, timedelta
import pytz
from sqlalchemy import select
from bot.database import async_session, User, UserCalendar
from bot.services.caldav_service import CalDAVService, test_caldav_connection
from bot.utils import encrypt_caldav_password
from bot.services.logger import send_log
import re

# Константы для ConversationHandler
EMAIL, PASSWORD = range(2)

# Базовый шаблон URL календаря
CALDAV_URL_TEMPLATE = "https://mail.id-east.ru/SOGo/dav/{username}/Calendar/personal/"

async def check_access(user_id):
    async with async_session() as session:
        user = await session.get(User, user_id)
        return user and user.is_approved and not user.is_blocked

async def today(update, context):
    if not await check_access(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    async with async_session() as session:
        result = await session.execute(select(UserCalendar).where(UserCalendar.user_id == update.effective_user.id))
        cal = result.scalars().first()
        if not cal:
            await update.message.reply_text("❌ Календарь не настроен.\nИспользуйте: /addcalendar")
            return

        is_ok, error = test_caldav_connection(cal.caldav_url, cal.caldav_username, cal.caldav_password_encrypted)
        if not is_ok:
            await update.message.reply_text(f"❌ Ошибка подключения к календарю: {error}\n\nПожалуйста, добавьте календарь заново через /addcalendar")
            return

        try:
            user_tz = pytz.timezone(cal.timezone)
            now = datetime.now(user_tz)
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day + timedelta(days=1)

            service = CalDAVService(cal.caldav_url, cal.caldav_username, cal.caldav_password_encrypted)
            all_events = service.get_events(start_of_day, end_of_day)
            # Убираем фильтр is_recurring - показываем ВСЕ события
            # all_events = [e for e in all_events if not e.get("is_recurring")]  # <-- УДАЛИТЬ ЭТУ СТРОКУ
            future_events = [e for e in all_events if e["start"] > now]

            if not future_events:
                await update.message.reply_text(f"📅 На сегодня ({now.strftime('%d.%m.%Y')}) встреч больше нет.", disable_web_page_preview=True)
                return

            msg = f"📅 <b>Встречи на сегодня ({now.strftime('%d.%m.%Y')}):</b>\n\n"
            for e in sorted(future_events, key=lambda x: x["start"]):
                st = e["start"].astimezone(user_tz).strftime("%H:%M")
                et = e["end"].astimezone(user_tz).strftime("%H:%M")
                # Добавляем пометку о повторяющемся событии
                recurring_mark = " 🔁" if e.get("is_recurring") else ""
                msg += f"🕐 {st} - {et}\n📌 {e['summary']}{recurring_mark}\n"
                if e["location"]:
                    msg += f"📍 {e['location']}\n"
                if e["attendees"]:
                    msg += f"👥 {', '.join(e['attendees'])}\n"
                msg += "\n"
            await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text("❌ Ошибка при получении встреч.")
            await send_log(f"❌ CalDAV ошибка для пользователя {update.effective_user.id}: {e}")

async def week(update, context):
    if not await check_access(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    async with async_session() as session:
        result = await session.execute(select(UserCalendar).where(UserCalendar.user_id == update.effective_user.id))
        cal = result.scalars().first()
        if not cal:
            await update.message.reply_text("❌ Календарь не настроен.\nИспользуйте: /addcalendar")
            return

        is_ok, error = test_caldav_connection(cal.caldav_url, cal.caldav_username, cal.caldav_password_encrypted)
        if not is_ok:
            await update.message.reply_text(f"❌ Ошибка подключения к календарю: {error}\n\nПожалуйста, добавьте календарь заново через /addcalendar")
            return

        try:
            user_tz = pytz.timezone(cal.timezone)
            now = datetime.now(user_tz)
            start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            monday = start_of_today - timedelta(days=start_of_today.weekday())
            sunday = monday + timedelta(days=7)

            service = CalDAVService(cal.caldav_url, cal.caldav_username, cal.caldav_password_encrypted)
            all_events = service.get_events(monday, sunday)
            # Убираем фильтр is_recurring - показываем ВСЕ события
            # all_events = [e for e in all_events if not e.get("is_recurring")]  # <-- УДАЛИТЬ ЭТУ СТРОКУ
            future_week_events = [e for e in all_events if e["start"] > now]

            if not future_week_events:
                await update.message.reply_text(f"📅 На этой неделе ({monday.strftime('%d.%m')} - {(sunday - timedelta(days=1)).strftime('%d.%m')}) больше нет встреч.", disable_web_page_preview=True)
                return

            msg = f"📅 <b>Все встречи на неделю ({monday.strftime('%d.%m')} - {(sunday - timedelta(days=1)).strftime('%d.%m')}):</b>\n\n"
            for e in sorted(future_week_events, key=lambda x: x["start"]):
                d = e["start"].astimezone(user_tz).strftime("%d.%m (%a)")
                st = e["start"].astimezone(user_tz).strftime("%H:%M")
                et = e["end"].astimezone(user_tz).strftime("%H:%M")
                # Добавляем пометку о повторяющемся событии
                recurring_mark = " 🔁" if e.get("is_recurring") else ""
                msg += f"📆 {d}\n🕐 {st} - {et}\n📌 {e['summary']}{recurring_mark}\n"
                if e["location"]:
                    msg += f"📍 {e['location']}\n"
                if e["attendees"]:
                    msg += f"👥 {', '.join(e['attendees'])}\n"
                msg += "\n"
            await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text("❌ Ошибка при получении встреч.")
            await send_log(f"❌ CalDAV ошибка для пользователя {update.effective_user.id}: {e}")

async def add_calendar_start(update, context):
    if not await check_access(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END
    
    context.user_data.clear()
    
    await update.message.reply_text(
        "📅 <b>Добавление календаря CalDAV</b>\n\n"
        "Введите ваш email (логин):\n"
        "Пример: user@id-east.ru\n\n"
        "URL календаря будет построен автоматически.\n\n"
        "/cancel — отмена",
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    return EMAIL

async def get_email(update, context):
    email = update.message.text.strip()
    
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        await update.message.reply_text(
            "❌ Неверный формат email. Попробуйте ещё раз:\n"
            "Пример: user@id-east.ru",
            disable_web_page_preview=True
        )
        return EMAIL
    
    context.user_data["calendar_email"] = email
    url = CALDAV_URL_TEMPLATE.format(username=email)
    context.user_data["calendar_url"] = url
    
    await update.message.reply_text(
        f"✅ Автоматически построен URL:\n<code>{url}</code>\n\n"
        "🔑 Введите пароль от календаря:",
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    return PASSWORD

async def get_password(update, context):
    password = update.message.text
    context.user_data["calendar_password"] = password
    
    # Удаляем сообщение с паролем
    try:
        await update.message.delete()
    except:
        pass
    
    await update.message.reply_text(
        "🔐 Проверяю подключение к календарю...",
        disable_web_page_preview=True
    )
    
    url = context.user_data.get("calendar_url")
    username = context.user_data.get("calendar_email")
    
    if not url or not username:
        await update.message.reply_text(
            "❌ Ошибка: данные календаря не найдены. Начните заново: /addcalendar",
            disable_web_page_preview=True
        )
        return ConversationHandler.END
    
    encrypted = encrypt_caldav_password(password)
    is_ok, error = test_caldav_connection(url, username, encrypted)

    if not is_ok:
        await update.message.reply_text(
            f"❌ Не удалось подключиться к календарю: {error}\n\n"
            "Проверьте правильность email и пароля.\n"
            "Попробуйте ещё раз: /addcalendar",
            disable_web_page_preview=True
        )
        return ConversationHandler.END

    async with async_session() as session:
        from sqlalchemy import delete
        await session.execute(delete(UserCalendar).where(UserCalendar.user_id == update.effective_user.id))

        cal = UserCalendar(
            user_id=update.effective_user.id,
            caldav_url=url,
            caldav_username=username,
            caldav_password_encrypted=encrypted
        )
        session.add(cal)
        await session.commit()
    
    await update.message.reply_text(
        "✅ Календарь успешно добавлен и проверен!\n\n"
        "Теперь вы можете использовать:\n"
        "• /today — встречи на сегодня\n"
        "• /week — встречи на неделю\n"
        "• /create_event — создать встречу\n"
        "• /create_zoom — создать Zoom встречу",
        disable_web_page_preview=True
    )
    return ConversationHandler.END

async def cancel(update, context):
    context.user_data.clear()
    await update.message.reply_text("❌ Операция отменена.")
    return ConversationHandler.END

# Для обратной совместимости со старыми именами
caldav_url = get_email
caldav_username = get_password
caldav_password = get_password