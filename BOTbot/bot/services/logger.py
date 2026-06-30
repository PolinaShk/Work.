from bot.config import BOT_TOKEN, LOGS_CHAT_ID, PROXY_URL
import logging

logger = logging.getLogger(__name__)

async def send_log(message: str):
    """Отправка лога в Telegram-чат"""
    if not LOGS_CHAT_ID:
        print(f"LOG (no chat): {message}")
        return
    try:
        import httpx
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        
        if len(message) > 4000:
            message = message[:3997] + "..."
        
        if PROXY_URL:
            async with httpx.AsyncClient(proxy=PROXY_URL) as client:
                await client.post(url, json={
                    "chat_id": LOGS_CHAT_ID,
                    "text": f"📋 {message}",
                    "parse_mode": "HTML"
                })
        else:
            async with httpx.AsyncClient() as client:
                await client.post(url, json={
                    "chat_id": LOGS_CHAT_ID,
                    "text": f"📋 {message}",
                    "parse_mode": "HTML"
                })
        print(f"LOG sent: {message[:100]}")
    except Exception as e:
        logger.error(f"Failed to send log: {e}")
        print(f"LOG failed: {e}")