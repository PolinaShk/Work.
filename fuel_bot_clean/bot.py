import requests
import time
import threading
from datetime import datetime, timedelta
import pytz
from api_helper import fetch_transaction_data
import config

TOKEN = config.TOKEN
API_URL = f"https://api.telegram.org/bot{TOKEN}/"
PROXIES = {
    'http': f'socks5://{config.PROXY_HOST}:{config.PROXY_PORT}',
    'https': f'socks5://{config.PROXY_HOST}:{config.PROXY_PORT}'
}

def format_number(num): 
    return "{:,.2f}".format(float(num or 0)).replace(",", " ")

def mask_card_number(num): 
    s = str(num)
    return s[:4] + '*' * (len(s)-10) + s[-6:] if len(s) > 10 else s

def send_message(chat_id, text):
    try:
        r = requests.post(API_URL + "sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=35, proxies=PROXIES)
        return r.ok
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        return False

def get_report():
    data = fetch_transaction_data()
    
    if not data:
        return "<b>📊 Ежедневный отчет по топливу</b>\n\n❌ Ошибка соединения с API. Попробуйте /sync позже."
    
    if not data.get('time_stack'):
        return f"<b>📊 Ежедневный отчет по топливу</b>\n\n<b>💰 Доступный остаток: {format_number(data.get('balance', 0))} руб.</b>\n\n❌ Нет данных о транзакциях за последний период."
    
    lines = []
    for i, (t, card, cost) in enumerate(zip(data['time_stack'], data['card_number_stack'], data['base_cost_5_stack']), 1):
        try: 
            dt = datetime.fromisoformat(t.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
        except: 
            dt = t
        comment = next((c for n, c in zip(data['number_stack'], data['comment_stack']) if str(card) == str(n)), "неизвестно")
        
        # 🔥 ИЗМЕНЕНИЕ: добавили пустую строку в конце для отступа между транзакциями
        lines.append(
            f"\n{i}. {dt}\n"
            f"Номер карты: {mask_card_number(card)}\n"
            f"Сумма: {format_number(cost)} руб.\n"
            f"Комментарий: {comment}\n"
        )

    return f"<b>📊 Ежедневный отчет по топливу</b>\n\n<b>💰 Доступный остаток: {format_number(data['balance'])} руб.</b>\n\n🔸 <b>Последние транзакции</b>\n{''.join(lines)}"

def scheduled_report():
    send_message(-1003687198964, get_report())
    print(f"✅ Отчет отправлен в {datetime.now(pytz.timezone('Europe/Moscow')).strftime('%Y-%m-%d %H:%M:%S')}")

def run_scheduler():
    moscow_tz = pytz.timezone('Europe/Moscow')
    print("⏰ Планировщик запущен. Отчеты в 9:15 MSK (пн-пт)")
    while True:
        now = datetime.now(moscow_tz)
        next_run = now.replace(hour=9, minute=15, second=0, microsecond=0)
        if now >= next_run: 
            next_run += timedelta(days=1)
        if next_run.weekday() < 5:
            print(f"⏰ Следующий отчет: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            time.sleep((next_run - now).total_seconds())
            if datetime.now(moscow_tz).weekday() < 5: 
                scheduled_report()

def main():
    print("🤖 БОТ ЗАПУЩЕН")
    threading.Thread(target=run_scheduler, daemon=True).start()
    
    last_id = 0
    try:
        r = requests.get(API_URL + "getUpdates", timeout=10, proxies=PROXIES)
        if r.ok:
            result = r.json().get("result", [])
            if result:
                last_id = result[-1]["update_id"]
                print(f"✅ Игнорируем сообщения до update_id: {last_id}")
    except:
        pass

    while True:
        try:
            r = requests.get(API_URL + "getUpdates", params={"timeout": 30, "offset": last_id + 1}, timeout=35, proxies=PROXIES)
            if r.ok:
                for u in r.json().get("result", []):
                    last_id = u["update_id"]
                    if "message" in u:
                        chat = u["message"]["chat"]["id"]
                        text = u["message"].get("text", "").strip()
                        
                        # 🔥 ИСПРАВЛЕНИЕ: убираем имя бота из команды
                        clean_text = text.split('@')[0] if '@' in text else text
                        
                        if clean_text in ["/start", "/sync"]:
                            send_message(chat, "🔄 Загрузка данных...")
                            send_message(chat, get_report())
                        elif clean_text == "/help":
                            send_message(chat, "/start - отчет\n/sync - синхронизация\n/help - помощь")
            time.sleep(1)
        except Exception as e:
            print(f"❌ Ошибка в цикле: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()