import requests
import base64
from datetime import datetime, timedelta
import pytz
from bot.utils import decrypt_caldav_password
import re
import logging

logger = logging.getLogger(__name__)

PROJECT_EMAIL = "mailbot@id-east.ru"

class CalDAVService:
    def __init__(self, url, username, encrypted_password):
        self.base_url = url.rstrip("/")
        self.ics_url = self.base_url + ".ics"
        self.username = username
        self.password = decrypt_caldav_password(encrypted_password)
        self.session = requests.Session()
        auth = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        self.session.headers.update({
            "Authorization": f"Basic {auth}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/calendar"
        })
        self.msk = pytz.timezone("Europe/Moscow")

    def get_events(self, start: datetime, end: datetime, timeout: int = 15):
        try:
            start_utc = start.astimezone(pytz.UTC) if start.tzinfo else pytz.UTC.localize(start)
            end_utc = end.astimezone(pytz.UTC) if end.tzinfo else pytz.UTC.localize(end)
            
            logger.info(f"Запрос событий с {start_utc} по {end_utc}")
            
            resp = self.session.get(self.ics_url, timeout=timeout)
            if resp.status_code == 401:
                raise Exception("401: Неверный логин или пароль")
            if resp.status_code == 404:
                raise Exception("404: Календарь не найден")
            if resp.status_code == 403:
                raise Exception("403: Доступ запрещён")
            if resp.status_code != 200:
                raise Exception(f"Ошибка сервера: {resp.status_code}")
            
            content = self._normalize_ics_content(resp.text)
            events = self._parse_ics(content, start_utc, end_utc)
            
            for event in events:
                if event["start"].tzinfo:
                    event["start"] = event["start"].astimezone(self.msk)
                if event["end"].tzinfo:
                    event["end"] = event["end"].astimezone(self.msk)
            
            logger.info(f"get_events: всего событий {len(events)}")
            return events
        except Exception as e:
            logger.error(f"get_events error: {e}")
            raise

    def _normalize_ics_content(self, content):
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        content = content.replace("&lt;", "<").replace("&gt;", ">")
        content = content.replace("&amp;", "&").replace("&quot;", '"')
        content = content.replace("&#39;", "'")
        lines = content.split("\n")
        normalized = []
        for line in lines:
            if line.startswith(" ") and normalized:
                normalized[-1] += line.strip()
            else:
                normalized.append(line)
        return "\n".join(normalized)

    def _parse_ics(self, content, range_start, range_end):
        events = []
        seen_keys = set()
        
        vevent_pattern = r'BEGIN:VEVENT(.*?)END:VEVENT'
        matches = re.findall(vevent_pattern, content, re.DOTALL | re.IGNORECASE)
        
        logger.info(f"Найдено {len(matches)} VEVENT блоков")
        
        for block in matches:
            event = self._parse_vevent(block)
            if not event:
                continue
            
            evt_start = event.get("start")
            evt_end = event.get("end")
            if not evt_start or not evt_end:
                continue
            
            rrule_str = event.get("rrule")
            
            # Обычное событие (без повторения)
            if not rrule_str:
                evt_start_utc = evt_start.astimezone(pytz.UTC) if evt_start.tzinfo else pytz.UTC.localize(evt_start)
                evt_end_utc = evt_end.astimezone(pytz.UTC) if evt_end.tzinfo else pytz.UTC.localize(evt_end)
                
                if evt_start_utc < range_end and evt_end_utc > range_start:
                    key = f"{event.get('uid', event['summary'])}_{evt_start_utc.timestamp()}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        events.append(event)
                continue
            
            # Повторяющееся событие
            logger.info(f"Обработка повторения: {event['summary']}, RRULE: {rrule_str}")
            
            # Приводим start к UTC
            if evt_start.tzinfo:
                dtstart = evt_start.astimezone(pytz.UTC)
            else:
                dtstart = pytz.UTC.localize(evt_start)
            
            duration = evt_end - evt_start
            
            # Парсим RRULE
            parts = rrule_str.upper().split(';')
            freq = None
            interval = 1
            byday = []
            until = None
            count = None
            
            for part in parts:
                if '=' not in part:
                    continue
                k, v = part.split('=', 1)
                if k == 'FREQ':
                    freq = v
                elif k == 'INTERVAL':
                    interval = int(v)
                elif k == 'BYDAY':
                    byday = v.split(',')
                elif k == 'UNTIL':
                    try:
                        # Убираем Z в конце если есть (UTC метка)
                        v_clean = v.rstrip('Z')
                        if 'T' in v_clean:
                            # Парсим дату и время
                            until = datetime.strptime(v_clean[:19], "%Y%m%dT%H%M%S")
                        else:
                            # Только дата
                            until = datetime.strptime(v_clean[:8], "%Y%m%d")
                        until = pytz.UTC.localize(until)
                        logger.info(f"  UNTIL: {until}")
                    except Exception as e:
                        logger.warning(f"  Ошибка парсинга UNTIL: {e}")
                elif k == 'COUNT':
                    count = int(v)
                    logger.info(f"  COUNT: {count}")
            
            weekdays = {'MO': 0, 'TU': 1, 'WE': 2, 'TH': 3, 'FR': 4, 'SA': 5, 'SU': 6}
            
            # Генерируем повторения
            generated = 0
            max_iterations = 500
            
            def add_event(occurrence_start, occurrence_end):
                nonlocal generated
                if occurrence_start < range_end and occurrence_end > range_start:
                    new_event = event.copy()
                    # Конвертируем в UTC если нужно
                    if not occurrence_start.tzinfo:
                        occurrence_start = pytz.UTC.localize(occurrence_start)
                    if not occurrence_end.tzinfo:
                        occurrence_end = pytz.UTC.localize(occurrence_end)
                    
                    new_event["start"] = occurrence_start
                    new_event["end"] = occurrence_end
                    new_event["is_recurring"] = True
                    key = f"{event.get('uid', event['summary'])}_{occurrence_start.timestamp()}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        events.append(new_event)
                        generated += 1
                        logger.debug(f"    Добавлено: {event['summary']} на {occurrence_start}")
                        return True
                return False
            
            # Добавляем оригинальное событие
            logger.info(f"  Оригинальное событие: {dtstart}")
            add_event(dtstart, dtstart + duration)
            
            if freq == 'DAILY':
                i = 1
                occurrence_num = 1
                while occurrence_num < max_iterations:
                    if i % interval == 0:
                        new_start = dtstart + timedelta(days=i)
                        
                        if until and new_start > until:
                            break
                        
                        new_end = new_start + duration
                        add_event(new_start, new_end)
                        occurrence_num += 1
                        
                        if count and occurrence_num >= count:
                            break
                    
                    i += 1
            
            elif freq == 'WEEKLY':
                week_num = 1
                occurrence_num = 1
                processed_weeks = 0
                
                while processed_weeks < max_iterations:
                    if week_num % interval == 0:
                        new_start = dtstart + timedelta(weeks=week_num)
                        
                        # Корректируем по BYDAY если есть
                        if byday:
                            if len(byday) == 1:
                                target_wd = weekdays.get(byday[0])
                                if target_wd is not None:
                                    days_ahead = target_wd - new_start.weekday()
                                    if days_ahead != 0:
                                        new_start += timedelta(days=days_ahead)
                            else:
                                # Для нескольких дней недели (MO,TU,WE)
                                current_wd = new_start.weekday()
                                target_wds = [weekdays.get(day) for day in byday if day in weekdays]
                                if target_wds:
                                    # Ищем следующий подходящий день
                                    found = False
                                    for offset in range(7):
                                        check_wd = (current_wd + offset) % 7
                                        if check_wd in target_wds:
                                            if offset > 0:
                                                new_start += timedelta(days=offset)
                                            found = True
                                            break
                                    if not found:
                                        new_start += timedelta(days=7)
                        
                        if until and new_start > until:
                            break
                        
                        new_end = new_start + duration
                        add_event(new_start, new_end)
                        occurrence_num += 1
                        
                        if count and occurrence_num >= count:
                            break
                    
                    week_num += 1
                    processed_weeks += 1
            
            elif freq == 'MONTHLY':
                month_num = 1
                occurrence_num = 1
                while occurrence_num < max_iterations:
                    if month_num % interval == 0:
                        # Простое месячное повторение (то же число месяца)
                        try:
                            new_start = dtstart + timedelta(days=30 * month_num)
                            # Корректируем до правильного дня в месяце
                            new_start = new_start.replace(day=min(dtstart.day, 
                                [31, 29 if new_start.year % 4 == 0 and (new_start.year % 100 != 0 or new_start.year % 400 == 0) else 28, 
                                 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][new_start.month - 1]))
                        except:
                            new_start = dtstart + timedelta(days=30 * month_num)
                        
                        if until and new_start > until:
                            break
                        
                        new_end = new_start + duration
                        add_event(new_start, new_end)
                        occurrence_num += 1
                        
                        if count and occurrence_num >= count:
                            break
                    
                    month_num += 1
            
            logger.info(f"  Для {event['summary']} сгенерировано {generated} повторений")
        
        events.sort(key=lambda x: x['start'])
        return events

    def _parse_vevent(self, block):
        event = {
            "summary": "Без названия",
            "start": None,
            "end": None,
            "location": "",
            "description": "",
            "attendees": [],
            "rrule": None,
            "uid": None,
            "organizer": None
        }
        
        lines = block.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            while i + 1 < len(lines) and lines[i + 1].startswith(' '):
                line += lines[i + 1].strip()
                i += 1
            
            if ':' not in line:
                i += 1
                continue
            
            key, value = line.split(':', 1)
            key = key.upper().split(';')[0]
            
            if key == 'SUMMARY':
                event["summary"] = value.strip()
            elif key == 'DTSTART':
                event["start"] = self._parse_date(value.strip(), line)
            elif key == 'DTEND':
                event["end"] = self._parse_date(value.strip(), line)
            elif key == 'LOCATION':
                event["location"] = value.strip()
            elif key == 'DESCRIPTION':
                event["description"] = value.strip()
            elif key == 'RRULE':
                event["rrule"] = value.strip()
            elif key == 'ATTENDEE':
                attendee = value.strip().replace("mailto:", "")
                if attendee and attendee not in event["attendees"]:
                    event["attendees"].append(attendee)
            elif key == 'ORGANIZER':
                event["organizer"] = value.strip().replace("mailto:", "")
            elif key == 'UID':
                event["uid"] = value.strip()
            
            i += 1
        
        if event["start"] and not event["end"]:
            event["end"] = event["start"] + timedelta(hours=1)
        
        return event if event["start"] and event["end"] else None

    def _parse_date(self, date_str, full_line=""):
        date_str = date_str.strip()
        
        if 'TZID=' in full_line:
            tz_match = re.search(r'TZID=([^:]+)', full_line)
            if tz_match:
                date_part = date_str
                if re.match(r'^\d{8}T\d{6}$', date_part):
                    try:
                        dt = datetime.strptime(date_part, "%Y%m%dT%H%M%S")
                        tz_name = tz_match.group(1)
                        try:
                            tz = pytz.timezone(tz_name)
                            return tz.localize(dt)
                        except:
                            return self.msk.localize(dt)
                    except:
                        pass
        
        if re.match(r'^\d{8}T\d{6}Z$', date_str):
            try:
                dt = datetime.strptime(date_str, "%Y%m%dT%H%M%SZ")
                return dt.replace(tzinfo=pytz.UTC)
            except:
                pass
        
        if re.match(r'^\d{8}T\d{6}$', date_str):
            try:
                dt = datetime.strptime(date_str, "%Y%m%dT%H%M%S")
                return self.msk.localize(dt)
            except:
                pass
        
        if re.match(r'^\d{8}$', date_str):
            try:
                dt = datetime.strptime(date_str, "%Y%m%d")
                return self.msk.localize(dt)
            except:
                pass
        
        return None

    def create_event(self, summary, start, end, location="", attendees=None, description=""):
        import time
        uid = f"{int(time.time())}_{abs(hash(summary))}@bot"
        
        if attendees is None:
            attendees = []
        
        final_attendees = set(attendees)
        final_attendees.add(PROJECT_EMAIL)
        if self.username:
            final_attendees.add(self.username)
        attendees = list(final_attendees)
        
        logger.info(f"create_event: отправка приглашений на email: {attendees}")
        
        attendee_str = ""
        for att in attendees:
            if att:
                attendee_str += f"ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{att}\n"
        
        organizer_str = f"ORGANIZER:mailto:{self.username}\n"
        
        if start.tzinfo:
            start_utc = start.astimezone(pytz.UTC)
        else:
            start_utc = self.msk.localize(start).astimezone(pytz.UTC)
        if end.tzinfo:
            end_utc = end.astimezone(pytz.UTC)
        else:
            end_utc = self.msk.localize(end).astimezone(pytz.UTC)
        
        start_str = start_utc.strftime('%Y%m%dT%H%M%SZ')
        end_str = end_utc.strftime('%Y%m%dT%H%M%SZ')
        now_str = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        summary = summary.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
        location = location.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
        description = description.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
        
        ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//TelegramBot//RU
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{now_str}
DTSTART:{start_str}
DTEND:{end_str}
SUMMARY:{summary}
LOCATION:{location}
DESCRIPTION:{description}
{organizer_str}{attendee_str}STATUS:CONFIRMED
SEQUENCE:0
END:VEVENT
END:VCALENDAR"""
        
        filename = f"{uid}.ics"
        put_url = f"{self.base_url}/{filename}"
        try:
            resp = self.session.put(
                put_url,
                data=ics.encode("utf-8"),
                headers={
                    "Content-Type": "text/calendar; charset=utf-8",
                    "If-None-Match": "*"
                },
                timeout=30
            )
            if resp.status_code in [201, 204]:
                logger.info(f"create_event: успешно создано для {self.username}")
                return True, uid
            raise Exception(f"Ошибка создания ({resp.status_code})")
        except Exception as e:
            logger.error(f"create_event ошибка: {e}")
            raise


def send_email_invite(to_email, subject, body, html_body=None, ics_content=None):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from bot.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
    
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        part1 = MIMEText(body, "plain", "utf-8")
        msg.attach(part1)
        if html_body:
            part2 = MIMEText(html_body, "html", "utf-8")
            msg.attach(part2)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info(f"Email отправлен на {to_email}")
        return True
    except Exception as e:
        logger.error(f"Email send error to {to_email}: {e}")
        return False


def test_caldav_connection(url, username, encrypted_password):
    try:
        service = CalDAVService(url, username, encrypted_password)
        tz = pytz.timezone("Europe/Moscow")
        now = datetime.now(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=30)
        service.get_events(start, end)
        return True, None
    except Exception as e:
        error_str = str(e)
        if "401" in error_str:
            return False, "Неверный пароль"
        elif "timeout" in error_str.lower():
            return False, "Таймаут подключения"
        else:
            return False, error_str[:100]