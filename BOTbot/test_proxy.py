import httpx 
import asyncio 
async def check(): 
    async with httpx.AsyncClient(proxy='socks5://192.168.2.100:8085') as c: 
        r = await c.get('https://api.telegram.org') 
        print(r.status_code) 
asyncio.run(check()) 
