import aiohttp
import base64
from datetime import datetime, timedelta
import pytz
from bot.config import ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET, PROXY_URL

class ZoomService:
    BASE_URL = "https://api.zoom.us/v2"

    def __init__(self):
        self.access_token = None
        self.token_expires_at = None
        self.session = None

    async def _get_session(self):
        if self.session is None:
            if PROXY_URL:
                from aiohttp_socks import ProxyConnector
                connector = ProxyConnector.from_url(PROXY_URL)
                self.session = aiohttp.ClientSession(connector=connector)
            else:
                self.session = aiohttp.ClientSession()
        return self.session

    async def _get_token(self):
        if self.access_token and self.token_expires_at and datetime.utcnow() < self.token_expires_at:
            return self.access_token

        session = await self._get_session()
        auth_str = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}"
        b64 = base64.b64encode(auth_str.encode()).decode()
        headers = {"Authorization": f"Basic {b64}"}
        params = {"grant_type": "account_credentials", "account_id": ZOOM_ACCOUNT_ID}

        async with session.post("https://zoom.us/oauth/token", params=params, headers=headers) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise Exception(f"Zoom OAuth Error: {data}")
            self.access_token = data["access_token"]
            self.token_expires_at = datetime.utcnow() + timedelta(seconds=data["expires_in"] - 60)
            return self.access_token

    async def check_conflicts(self, start_time, end_time):
        token = await self._get_token()
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {token}"}

        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        params = {"page_size": 100, "from": start_str, "to": end_str, "type": "upcoming"}
        url = f"{self.BASE_URL}/users/me/meetings"

        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status != 200:
                error = await resp.json()
                raise Exception(f"Zoom API error: {error}")
            data = await resp.json()
            meetings = data.get("meetings", [])
            conflicts = []
            for m in meetings:
                m_start = datetime.strptime(m["start_time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
                m_end = m_start + timedelta(minutes=m.get("duration", 60))
                if m_start < end_time and m_end > start_time:
                    conflicts.append({
                        "id": m["id"],
                        "topic": m["topic"],
                        "start_time": m["start_time"],
                        "host_email": m.get("host_email", "Unknown")
                    })
            return conflicts

    async def create_meeting(self, topic, start_time, duration_min=60, attendees=None):
        token = await self._get_token()
        session = await self._get_session()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        invitees = []
        if attendees:
            for email in attendees:
                if email and email != "project@id-east.ru" and email != "mailbot@id-east.ru":
                    if "@" in email and "." in email:
                        invitees.append({"email": email})
        
        payload = {
            "topic": topic,
            "type": 2,
            "start_time": start_time.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration": duration_min,
            "timezone": "Europe/Moscow",
            "settings": {
                "host_video": True,
                "participant_video": True,
                "join_before_host": False,
                "mute_upon_entry": True,
                "waiting_room": True,
                "approval_type": 0,
                "audio": "both",
                "auto_recording": "none",
                "alternative_hosts": "",
                "alternative_hosts_email_notification": False
            }
        }
        
        url = f"{self.BASE_URL}/users/me/meetings"
        async with session.post(url, headers=headers, json=payload) as resp:
            data = await resp.json()
            if resp.status != 201:
                raise Exception(f"Zoom create error: {data}")
            
            meeting = {
                "id": data["id"],
                "join_url": data["join_url"],
                "password": data.get("password", "")
            }
            
            if invitees:
                await self._add_registrants(meeting["id"], invitees)
            
            return meeting
    
    async def _add_registrants(self, meeting_id, registrants):
        token = await self._get_token()
        session = await self._get_session()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        url = f"{self.BASE_URL}/meetings/{meeting_id}/registrants"
        
        for registrant in registrants:
            payload = {
                "email": registrant["email"],
                "first_name": registrant["email"].split("@")[0],
                "last_name": "",
                "auto_approve": True
            }
            try:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status not in [201, 204]:
                        print(f"Failed to add registrant {registrant['email']}: {await resp.text()}")
            except Exception as e:
                print(f"Error adding registrant: {e}")

    async def close(self):
        if self.session:
            await self.session.close()