from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime, timedelta
import pytz
from sqlalchemy import select
from bot.database import async_session, User, UserCalendar
from bot.services.zoom_service import ZoomService
from bot.services.logger import send_log
import logging

logger = logging.getLogger(__name__)

async def check_access(user_id):
    async with async_session() as session:
        user = await session.get(User, user_id)
        return user and user.is_approved and not user.is_blocked

async def upcoming_zoom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    
    status_msg = await update.message.reply_text("🔍 Загружаю ближайшие Zoom встречи...", disable_web_page_preview=True)
    
    async with async_session() as session:
        result = await session.execute(select(UserCalendar).where(UserCalendar.user_id == update.effective_user.id))
        cal = result.scalars().first()
        
        if not cal:
            await status_msg.edit_text("❌ Календарь не настроен.\nИспользуйте: /addcalendar")
            return
        
        try:
            zoom = ZoomService()
            user_tz = pytz.timezone(cal.timezone)
            now = datetime.now(user_tz)
            now_utc = now.astimezone(pytz.UTC)
            end_utc = now_utc + timedelta(days=30)
            
            conflicts = await zoom.check_conflicts(now_utc, end_utc)
            await zoom.close()
            
            if not conflicts:
                await status_msg.edit_text("🎥 Нет предстоящих Zoom встреч в следующие 30 дней.")
                return
            
            zoom_meetings = []
            for meeting in conflicts:
                start_time = datetime.strptime(meeting["start_time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
                start_time_msk = start_time.astimezone(user_tz)
                
                zoom_meetings.append({
                    "summary": meeting["topic"],
                    "start": start_time_msk,
                    "end": start_time_msk + timedelta(minutes=60),
                    "join_url": meeting.get("join_url", ""),
                    "id": meeting["id"]
                })
            
            zoom_meetings.sort(key=lambda x: x["start"])
            zoom_meetings = zoom_meetings[:10]
            
            msg = "🎥 <b>10 ближайших Zoom встреч:</b>\n\n"
            
            for i, meeting in enumerate(zoom_meetings, 1):
                start_time = meeting["start"].strftime("%d.%m.%Y %H:%M")
                end_time = meeting["end"].strftime("%H:%M")
                
                msg += f"<b>{i}. {meeting['summary']}</b>\n"
                msg += f"   📅 {start_time} - {end_time}\n"
            
            await status_msg.edit_text(msg, parse_mode="HTML", disable_web_page_preview=True)
            
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка при получении Zoom встреч: {str(e)[:200]}")
            await send_log(f"❌ Ошибка upcoming_zoom для пользователя {update.effective_user.id}: {e}")