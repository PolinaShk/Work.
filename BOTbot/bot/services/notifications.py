from datetime import datetime, timedelta
import pytz
from sqlalchemy import select
from bot.database import async_session, User, UserCalendar
from bot.services.caldav_service import CalDAVService
import logging

logger = logging.getLogger(__name__)

# ЯВНО указываем часовой пояс
MSK = pytz.timezone("Europe/Moscow")

async def send_notifications(application):
    # Принудительно используем MSK
    now = datetime.now(MSK)
    
    # Отладка - пишем всегда
    logger.info(f"[NOTIFY] Проверка в {now.strftime('%Y-%m-%d %H:%M:%S')} MSK")
    
    # Проверяем только 45-ю минуту
    if now.minute != 45:
        return
    
    logger.info(f"[NOTIFY] ✅ Минута 45! Час: {now.hour}")
    
    # Проверяем 8-й час
    if now.hour != 9:
        logger.info(f"[NOTIFY] Сейчас {now.hour}:00, а нужно 8:45, пропускаем")
        return
    
    logger.info(f"[NOTIFY] ✅ Час 8! ОТПРАВЛЯЕМ УВЕДОМЛЕНИЯ!")
    
    async with async_session() as session:
        result = await session.execute(
            select(UserCalendar).join(User).where(
                User.is_approved == True, 
                User.is_blocked == False
            )
        )
        calendars = result.scalars().all()
        
        logger.info(f"[NOTIFY] Найдено календарей: {len(calendars)}")
        
        for cal in calendars:
            user_tz = pytz.timezone(cal.timezone)
            local_now = now.astimezone(user_tz)
            weekday = local_now.weekday()
            
            logger.info(f"[NOTIFY] User {cal.user_id}: daily={cal.notification_daily}, weekly={cal.notification_weekly}, weekday={weekday}")
            
            # === ЕЖЕДНЕВНЫЕ (ПН-ПТ) ===
            if cal.notification_daily and weekday < 5:
                logger.info(f"[NOTIFY] Отправка ежедневного уведомления {cal.user_id}")
                start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=1)
                
                try:
                    service = CalDAVService(cal.caldav_url, cal.caldav_username, cal.caldav_password_encrypted)
                    all_events = service.get_events(start, end)
                    future_events = [e for e in all_events if e["start"] > local_now]
                    
                    if future_events:
                        msg = f"🔔 <b>Ваши встречи сегодня ({local_now.strftime('%d.%m.%Y')}):</b>\n\n"
                        for e in sorted(future_events, key=lambda x: x["start"]):
                            st = e["start"].astimezone(user_tz).strftime("%H:%M")
                            et = e["end"].astimezone(user_tz).strftime("%H:%M")
                            recurring = " 🔁" if e.get("is_recurring") else ""
                            msg += f"🕐 {st} - {et}\n📌 {e['summary']}{recurring}\n"
                            if e.get("location"):
                                msg += f"📍 {e['location']}\n"
                            msg += "\n"
                        
                        await application.bot.send_message(chat_id=cal.user_id, text=msg, parse_mode="HTML")
                        logger.info(f"[NOTIFY] ✅ Отправлено {cal.user_id}")
                    else:
                        logger.info(f"[NOTIFY] Нет событий для {cal.user_id}")
                except Exception as e:
                    logger.error(f"[NOTIFY] Ошибка: {e}")
            
            # === ЕЖЕНЕДЕЛЬНЫЕ (ПОНЕДЕЛЬНИК) ===
            if cal.notification_weekly and weekday == 0:
                logger.info(f"[NOTIFY] Отправка еженедельного уведомления {cal.user_id}")
                start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=7)
                
                try:
                    service = CalDAVService(cal.caldav_url, cal.caldav_username, cal.caldav_password_encrypted)
                    all_events = service.get_events(start, end)
                    week_events = [e for e in all_events if e["start"] > local_now]
                    
                    if week_events:
                        msg = f"🔔 <b>Ваши встречи на неделю ({start.strftime('%d.%m')} - {(end - timedelta(days=1)).strftime('%d.%m')}):</b>\n\n"
                        current_date = None
                        for e in sorted(week_events, key=lambda x: x["start"]):
                            start_local = e["start"].astimezone(user_tz)
                            end_local = e["end"].astimezone(user_tz)
                            date_str = start_local.strftime("%d.%m (%a)")
                            
                            if date_str != current_date:
                                current_date = date_str
                                msg += f"📅 <b>{date_str}</b>\n"
                            
                            recurring = " 🔁" if e.get("is_recurring") else ""
                            msg += f"   🕐 {start_local.strftime('%H:%M')} - {end_local.strftime('%H:%M')}\n"
                            msg += f"   📌 {e['summary']}{recurring}\n"
                            msg += "\n"
                        
                        await application.bot.send_message(chat_id=cal.user_id, text=msg, parse_mode="HTML")
                        logger.info(f"[NOTIFY] ✅ Отправлено {cal.user_id}")
                    else:
                        logger.info(f"[NOTIFY] Нет событий для {cal.user_id}")
                except Exception as e:
                    logger.error(f"[NOTIFY] Ошибка: {e}")

logger.info("[NOTIFY] Модуль уведомлений загружен с MSK")