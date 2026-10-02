"""Живой e2e: подписка менеджера по ссылке, отказ на чужой контакт, уведомление о новой заявке."""
import asyncio, sqlite3, sys
sys.path.insert(0, "ops"); from salat import acc, sess, TelegramClient, StringSession
from telethon.tl.types import InputMediaContact
BOT = "minicrm_agency_leads_bot"
import httpx, re
BASE = "https://crm.213-32-66-46.nip.io"
env = dict(l.split("=", 1) for l in open(".env").read().splitlines() if "=" in l)
w = httpx.Client(headers={"origin": BASE}, follow_redirects=True)
w.post(BASE + "/login", data={"username": "demo", "password": env["DEMO_PASSWORD"]})
tok = re.search(r"start=m_([A-Za-z0-9]+)", w.get(BASE + "/settings").text).group(1)
print("ссылка из настроек получена")
async def say(c, t, wait=2.5):
    await c.send_message(BOT, t); await asyncio.sleep(wait)
    m = (await c.get_messages(BOT, limit=1))[0]; print(">>", str(t)[:40], "\n<<", m.raw_text[:140].replace("\n", " | ")); return m
async def main():
    async with TelegramClient(StringSession(sess), acc["api_id"], acc["api_hash"]) as c:
        await say(c, f"/start m_{tok}")
        await say(c, "/start"); await say(c, "Проверка уведомлений")
        await c.send_file(BOT, InputMediaContact(phone_number="+70000000000", first_name="Чужой", last_name="", vcard=""))
        await asyncio.sleep(2.5); print("<< (чужой контакт)", (await c.get_messages(BOT, limit=1))[0].raw_text[:100])
        await say(c, "+7 900 000-00-01")
        m = await say(c, "Тестовая заявка для проверки уведомления")
        await m.click(text="Отправить"); await asyncio.sleep(4)
        for x in reversed(await c.get_messages(BOT, limit=2)):
            btn = [b.url for row in (x.buttons or []) for b in row if getattr(b, "url", None)]
            print("<<", x.raw_text[:160].replace("\n", " | "), btn)
        await say(c, "/stop")
asyncio.run(main())
