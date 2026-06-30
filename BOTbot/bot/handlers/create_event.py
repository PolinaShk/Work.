from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler
from datetime import datetime, timedelta
import pytz
from sqlalchemy import select
from bot.database import async_session, User, UserCalendar
from bot.services.caldav_service import CalDAVService, send_email_invite
from bot.services.logger import send_log
import logging

logger = logging.getLogger(__name__)

EVT_SUMMARY, EVT_START, EVT_DURATION, EVT_LOCATION, EVT_ATTENDEES = range(5)
FORCE_CREATE = 99
FIND_FREE_TIME = 100

PROJECT_EMAIL = "mailbot@id-east.ru"
INCLUDE_WEEKENDS = False

async def safe_edit_message(message_obj, text, parse_mode=None, reply_markup=None, disable_web_page_preview=None):
    try:
        if hasattr(message_obj, 'edit_text'):
            await message_obj.edit_text(
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview
            )
        elif hasattr(message_obj, 'edit_message_text'):
            await message_obj.edit_message_text(
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview
            )
        return True
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise e
        return False

async def check_access(user_id):
    async with async_session() as session:
        user = await session.get(User, user_id)
        return user and user.is_approved and not user.is_blocked

def add_required_attendees(attendees, author_email):
    required = set()
    required.add(PROJECT_EMAIL)
    if author_email:
        required.add(author_email)
    for attendee in attendees:
        if attendee and attendee.strip():
            required.add(attendee.strip())
    return list(required)

def validate_start_time(start_dt):
    now = datetime.now(pytz.timezone("Europe/Moscow"))
    min_allowed = now + timedelta(minutes=15)
    if start_dt < min_allowed:
        return False, min_allowed
    return True, None

def send_regular_email_invites(summary, start, end, location, attendees, organizer_email):
    result = {"emailed": [], "failed": []}
    if not attendees:
        return result
    
    start_msk = start.astimezone(pytz.timezone("Europe/Moscow")) if start.tzinfo else pytz.timezone("Europe/Moscow").localize(start)
    end_msk = end.astimezone(pytz.timezone("Europe/Moscow")) if end.tzinfo else pytz.timezone("Europe/Moscow").localize(end)
    
    subject = f"Приглашение на встречу: {summary}"
    location_text = location if location else "не указано"
    
    body_text = f"""
Приглашение на встречу: {summary}

Дата и время: {start_msk.strftime('%d.%m.%Y %H:%M')} - {end_msk.strftime('%H:%M')}
Место: {location_text}

Организатор: {organizer_email}

---
Это приглашение создано автоматически через Telegram бота iCalendarPM.
    """
    
    body_html = f"""
<html>
<body>
<h2>Приглашение на встречу: {summary}</h2>
<p><b>Дата и время:</b> {start_msk.strftime('%d.%m.%Y %H:%M')} - {end_msk.strftime('%H:%M')}</p>
<p><b>Место:</b> {location_text}</p>
<p><b>Организатор:</b> {organizer_email}</p>
<hr>
<p><small>Это приглашение создано автоматически через Telegram бота iCalendarPM.</small></p>
</body>
</html>
    """
    
    for attendee in attendees:
        if attendee:
            if send_email_invite(attendee, subject, body_text, body_html, None):
                result["emailed"].append(attendee)
            else:
                result["failed"].append(attendee)
    
    return result

async def create_event_start(update, context):
    if not await check_access(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END
    
    context.user_data.clear()
    
    await update.message.reply_text(
        "📝 <b>Создание новой встречи</b>\n\n"
        "Введите название встречи:\n\n"
        "(для отмены отправьте /cancel)",
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    return EVT_SUMMARY

async def event_summary(update, context):
    context.user_data["event_summary"] = update.message.text
    await update.message.reply_text(
        "📅 Введите дату и время начала (ДД.ММ.ГГГГ ЧЧ:ММ):\n"
        "Например: 13.05.2026 14:30",
        disable_web_page_preview=True
    )
    return EVT_START

async def event_start_time(update, context):
    try:
        dt = datetime.strptime(update.message.text, "%d.%m.%Y %H:%M")
        tz = pytz.timezone("Europe/Moscow")
        start_dt = tz.localize(dt)
        
        is_valid, min_time = validate_start_time(start_dt)
        if not is_valid:
            await update.message.reply_text(
                f"❌ Нельзя создавать встречи в прошлом или менее чем через 15 минут.\n\n"
                f"🕐 Минимальное время: {min_time.strftime('%d.%m.%Y %H:%M')}",
                disable_web_page_preview=True
            )
            return EVT_START
        
        context.user_data["event_start_time"] = start_dt
        await update.message.reply_text(
            "⏱ Введите длительность в минутах (15-480):\n"
            "Например: 60",
            disable_web_page_preview=True
        )
        return EVT_DURATION
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат. Используйте: ДД.ММ.ГГГГ ЧЧ:ММ",
            disable_web_page_preview=True
        )
        return EVT_START

async def event_duration(update, context):
    try:
        d = int(update.message.text)
        if d < 15 or d > 480:
            raise ValueError
        context.user_data["event_duration"] = d
        await update.message.reply_text(
            "📍 Введите место встречи (или - чтобы пропустить):",
            disable_web_page_preview=True
        )
        return EVT_LOCATION
    except ValueError:
        await update.message.reply_text(
            "❌ Введите число от 15 до 480 (минут):",
            disable_web_page_preview=True
        )
        return EVT_DURATION

async def event_location(update, context):
    location = update.message.text
    context.user_data["event_location"] = location if location != "-" else ""
    await update.message.reply_text(
        "👥 Введите email участников через запятую (или - чтобы пропустить):\n"
        "Пример: user1@example.com, user2@example.com",
        disable_web_page_preview=True
    )
    return EVT_ATTENDEES

def find_all_free_slots(service, start_date, duration, max_days=14, max_slots=10):
    work_start = 9
    work_end = 18
    step_minutes = 15
    
    all_free_slots = []
    selected_day = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    
    day_offset = 0
    days_checked = 0
    
    while len(all_free_slots) < max_slots and days_checked <= max_days:
        current_day = selected_day + timedelta(days=day_offset)
        
        if not INCLUDE_WEEKENDS and current_day.weekday() >= 5:
            day_offset += 1
            continue
        
        current = current_day.replace(hour=work_start, minute=0, second=0, microsecond=0)
        day_end = current_day.replace(hour=work_end, minute=0, second=0, microsecond=0)
        
        if day_offset == 0 and start_date.hour >= work_start:
            current = start_date
            minutes = current.minute
            remainder = minutes % step_minutes
            if remainder != 0:
                current = current.replace(minute=minutes + (step_minutes - remainder), second=0, microsecond=0)
        
        while current < day_end and len(all_free_slots) < max_slots:
            slot_end = current + timedelta(minutes=duration)
            
            if slot_end > day_end:
                break
            
            try:
                events = service.get_events(current, slot_end)
                conflicts = [e for e in events if e["start"] < slot_end and e["end"] > current]
                
                if not conflicts:
                    all_free_slots.append(current)
                    current += timedelta(minutes=step_minutes)
                else:
                    conflict_end = max([e["end"] for e in conflicts])
                    current = conflict_end
                    minutes = current.minute
                    remainder = minutes % step_minutes
                    if remainder != 0:
                        current = current.replace(minute=minutes + (step_minutes - remainder), second=0, microsecond=0)
            except Exception as e:
                logger.error(f"Ошибка проверки слота: {e}")
                current += timedelta(minutes=step_minutes)
        
        day_offset += 1
        days_checked += 1
    
    return all_free_slots

async def event_attendees(update, context):
    text = update.message.text
    user_attendees = []
    if text != "-":
        user_attendees = [email.strip() for email in text.split(",") if email.strip()]
    
    context.user_data["event_attendees"] = user_attendees
    
    start = context.user_data["event_start_time"]
    duration = context.user_data["event_duration"]
    end = start + timedelta(minutes=duration)
    summary = context.user_data["event_summary"]
    location = context.user_data["event_location"]
    
    status_msg = await update.message.reply_text("🔍 Проверяю календарь...", disable_web_page_preview=True)
    
    async with async_session() as session:
        result = await session.execute(select(UserCalendar).where(UserCalendar.user_id == update.effective_user.id))
        cal = result.scalars().first()
        
        if not cal:
            await safe_edit_message(status_msg, "❌ Сначала добавьте календарь: /addcalendar")
            return ConversationHandler.END
        
        try:
            service = CalDAVService(cal.caldav_url, cal.caldav_username, cal.caldav_password_encrypted)
            existing_events = service.get_events(start, end)
            conflicts = [e for e in existing_events if e["start"] < end and e["end"] > start]
            
            if conflicts:
                context.user_data["original_start_time"] = start
                msg = "⚠️ <b>Обнаружены конфликты:</b>\n\n"
                for e in sorted(conflicts, key=lambda x: x["start"])[:5]:
                    st = e["start"].astimezone(pytz.timezone("Europe/Moscow")).strftime("%d.%m.%Y %H:%M")
                    et = e["end"].astimezone(pytz.timezone("Europe/Moscow")).strftime("%H:%M")
                    msg += f"📌 <b>{e['summary']}</b>\n🕐 {st} - {et}\n\n"
                msg += "Что делаем?"
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Да, создать", callback_data="force_create")],
                    [InlineKeyboardButton("🔍 Найти свободное время", callback_data="find_free_time")],
                    [InlineKeyboardButton("❌ Отмена", callback_data="cancel_create")]
                ])
                await safe_edit_message(status_msg, msg, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True)
                return FORCE_CREATE
            
            await safe_edit_message(status_msg, "⏳ Создаю встречу...", disable_web_page_preview=True)
            attendees = add_required_attendees(user_attendees, cal.caldav_username)
            description = f"Встреча создана через Telegram бота iCalendarPM\n"
            if attendees:
                description += f"\nУчастники: {', '.join(attendees)}\n"
            
            success, uid = service.create_event(summary, start, end, location, attendees, description)
            
            if success:
                email_result = send_regular_email_invites(summary, start, end, location, attendees, cal.caldav_username)
                # Скрываем mailbot@id-east.ru из вывода
                display_attendees = [att for att in attendees if att != PROJECT_EMAIL]
                msg = f"✅ <b>Встреча создана!</b>\n\n"
                msg += f"📌 <b>{summary}</b>\n"
                msg += f"🕐 {start.strftime('%d.%m.%Y %H:%M')} - {end.strftime('%H:%M')}\n"
                if location:
                    msg += f"📍 {location}\n"
                if display_attendees:
                    msg += f"\n👥 <b>Участники:</b>\n"
                    for att in display_attendees:
                        msg += f"• {att}\n"
                msg += f"\n📧 Приглашения отправлены на email участников."
                await safe_edit_message(status_msg, msg, parse_mode="HTML", disable_web_page_preview=True)
                await send_log(f"✅ Пользователь {update.effective_user.id} создал встречу: {summary}")
            else:
                await safe_edit_message(status_msg, "❌ Ошибка при создании встречи")
        except Exception as e:
            await safe_edit_message(status_msg, f"❌ Ошибка: {str(e)[:200]}")
            await send_log(f"❌ Ошибка создания встречи: {e}")
    
    return ConversationHandler.END

async def force_create_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_create":
        await safe_edit_message(query, "❌ Отменено.")
        return ConversationHandler.END
    
    if query.data == "find_free_time":
        await safe_edit_message(query, "🔍 Ищу свободное время...", disable_web_page_preview=True)
        return await find_free_time_handler(update, context)
    
    summary = context.user_data.get("event_summary")
    start = context.user_data.get("event_start_time")
    duration = context.user_data.get("event_duration")
    location = context.user_data.get("event_location", "")
    user_attendees = context.user_data.get("event_attendees", [])
    
    if not all([summary, start, duration]):
        await safe_edit_message(query, "❌ Данные утеряны. Начните заново: /create_event")
        return ConversationHandler.END
    
    end = start + timedelta(minutes=duration)
    await safe_edit_message(query, "⏳ Создаю встречу...", disable_web_page_preview=True)
    
    async with async_session() as session:
        result = await session.execute(select(UserCalendar).where(UserCalendar.user_id == update.effective_user.id))
        cal = result.scalars().first()
        if not cal:
            await safe_edit_message(query, "❌ Календарь не найден.")
            return ConversationHandler.END
        
        try:
            service = CalDAVService(cal.caldav_url, cal.caldav_username, cal.caldav_password_encrypted)
            attendees = add_required_attendees(user_attendees, cal.caldav_username)
            description = f"Встреча создана через Telegram бота iCalendarPM\n"
            success, uid = service.create_event(summary, start, end, location, attendees, description)
            
            if success:
                email_result = send_regular_email_invites(summary, start, end, location, attendees, cal.caldav_username)
                display_attendees = [att for att in attendees if att != PROJECT_EMAIL]
                msg = f"✅ <b>Встреча создана!</b>\n\n"
                msg += f"📌 <b>{summary}</b>\n"
                msg += f"🕐 {start.strftime('%d.%m.%Y %H:%M')} - {end.strftime('%H:%M')}\n"
                if location:
                    msg += f"📍 {location}\n"
                if display_attendees:
                    msg += f"\n👥 <b>Участники:</b>\n"
                    for att in display_attendees:
                        msg += f"• {att}\n"
                msg += f"\n⚠️ Встреча создана, несмотря на конфликты."
                await safe_edit_message(query, msg, parse_mode="HTML", disable_web_page_preview=True)
                await send_log(f"✅ Пользователь {update.effective_user.id} создал встречу (вопреки конфликту): {summary}")
            else:
                await safe_edit_message(query, "❌ Ошибка при создании")
        except Exception as e:
            await safe_edit_message(query, f"❌ Ошибка: {str(e)[:200]}")
    
    return ConversationHandler.END

async def find_free_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_find_free_time":
        await safe_edit_message(query, "❌ Поиск отменён.")
        return ConversationHandler.END
    
    summary = context.user_data.get("event_summary")
    duration = context.user_data.get("event_duration")
    location = context.user_data.get("event_location", "")
    user_attendees = context.user_data.get("event_attendees", [])
    original_start = context.user_data.get("original_start_time")
    
    if not all([summary, duration, original_start]):
        await safe_edit_message(query, "❌ Данные утеряны.")
        return ConversationHandler.END
    
    await safe_edit_message(query, "🔍 Ищу свободное время...", disable_web_page_preview=True)
    
    async with async_session() as session:
        result = await session.execute(select(UserCalendar).where(UserCalendar.user_id == update.effective_user.id))
        cal = result.scalars().first()
        if not cal:
            await safe_edit_message(query, "❌ Календарь не найден.")
            return ConversationHandler.END
        
        try:
            service = CalDAVService(cal.caldav_url, cal.caldav_username, cal.caldav_password_encrypted)
            free_slots = find_all_free_slots(service, original_start, duration, max_days=14, max_slots=10)
            
            if not free_slots:
                await safe_edit_message(query, "❌ Не найдено свободное время.")
                return ConversationHandler.END
            
            context.user_data["free_slots"] = {slot.timestamp(): slot for slot in free_slots}
            keyboard_buttons = []
            weekdays_ru = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
            
            for slot in free_slots[:10]:
                slot_end = slot + timedelta(minutes=duration)
                weekday = weekdays_ru[slot.weekday()]
                button_text = f"{weekday} {slot.strftime('%d.%m.%Y %H:%M')} - {slot_end.strftime('%H:%M')}"
                keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=f"free_slot_{slot.timestamp()}")])
            
            keyboard_buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_find_free_time")])
            keyboard = InlineKeyboardMarkup(keyboard_buttons)
            
            msg = f"🔍 <b>Найдено {len(free_slots)} свободных окон:</b>\n\n📌 {summary} ({duration} мин)\n\nВыберите время:"
            await safe_edit_message(query, msg, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True)
            return FIND_FREE_TIME
        except Exception as e:
            await safe_edit_message(query, f"❌ Ошибка: {str(e)[:200]}")
            return ConversationHandler.END

async def find_free_time_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_find_free_time":
        await safe_edit_message(query, "❌ Отменено.")
        return ConversationHandler.END
    
    if query.data.startswith("free_slot_"):
        try:
            timestamp = float(query.data.split("_")[2])
        except (IndexError, ValueError):
            await safe_edit_message(query, "❌ Ошибка формата.")
            return ConversationHandler.END
        
        start = context.user_data.get("free_slots", {}).get(timestamp)
        if not start:
            await safe_edit_message(query, "❌ Время больше недоступно.")
            return ConversationHandler.END
        
        summary = context.user_data.get("event_summary")
        duration = context.user_data.get("event_duration")
        location = context.user_data.get("event_location", "")
        user_attendees = context.user_data.get("event_attendees", [])
        end = start + timedelta(minutes=duration)
        
        await safe_edit_message(query, "⏳ Создаю встречу...", disable_web_page_preview=True)
        
        async with async_session() as session:
            result = await session.execute(select(UserCalendar).where(UserCalendar.user_id == update.effective_user.id))
            cal = result.scalars().first()
            if not cal:
                await safe_edit_message(query, "❌ Календарь не найден.")
                return ConversationHandler.END
            
            try:
                service = CalDAVService(cal.caldav_url, cal.caldav_username, cal.caldav_password_encrypted)
                attendees = add_required_attendees(user_attendees, cal.caldav_username)
                description = f"Встреча создана через Telegram бота iCalendarPM\n"
                success, uid = service.create_event(summary, start, end, location, attendees, description)
                
                if success:
                    email_result = send_regular_email_invites(summary, start, end, location, attendees, cal.caldav_username)
                    display_attendees = [att for att in attendees if att != PROJECT_EMAIL]
                    msg = f"✅ <b>Встреча создана!</b>\n\n"
                    msg += f"📌 <b>{summary}</b>\n"
                    msg += f"🕐 {start.strftime('%d.%m.%Y %H:%M')} - {end.strftime('%H:%M')}\n"
                    if location:
                        msg += f"📍 {location}\n"
                    if display_attendees:
                        msg += f"\n👥 <b>Участники:</b>\n"
                        for att in display_attendees:
                            msg += f"• {att}\n"
                    await safe_edit_message(query, msg, parse_mode="HTML", disable_web_page_preview=True)
                    await send_log(f"✅ Пользователь создал встречу в свободное время: {summary}")
                else:
                    await safe_edit_message(query, "❌ Ошибка при создании")
            except Exception as e:
                await safe_edit_message(query, f"❌ Ошибка: {str(e)[:200]}")
    
    return ConversationHandler.END

async def cancel(update, context):
    context.user_data.clear()
    await update.message.reply_text("❌ Создание встречи отменено.")
    return ConversationHandler.END