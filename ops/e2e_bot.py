"""Живой e2e п.1: пользователь проходит анкету в боте → лид в CRM + событие в SSE."""
import asyncio, os, sys, json
sys.path.insert(0, "ops"); from salat import acc, sess, TelegramClient, StringSession
import httpx
BASE = "https://crm.213-32-66-46.nip.io"
BOT = "minicrm_agency_leads_bot"
env = dict(l.split("=", 1) for l in open(".env").read().splitlines() if "=" in l)

async def sse_listen(c, got):
    async with c.stream("GET", BASE + "/events") as r:
        async for line in r.aiter_lines():
            if line.startswith("data:"):
                got.append(json.loads(line[5:])); return

async def last(c):
    await asyncio.sleep(2.5)
    return (await c.get_messages(BOT, limit=1))[0]

async def main():
    web = httpx.AsyncClient(headers={"origin": BASE}, timeout=60)
    r = await web.post(BASE + "/login", data={"username": "demo", "password": env["DEMO_PASSWORD"]})
    assert r.status_code in (200, 303), r.status_code
    got = []
    listener = asyncio.create_task(sse_listen(web, got))
    async with TelegramClient(StringSession(sess), acc["api_id"], acc["api_hash"]) as c:
        for text in ["/start", "Тест Е2Е", "+7 700 000 00 00", "Нужен лендинг для курса, запуск через 2 недели"]:
            await c.send_message(BOT, text)
            m = await last(c)
            print(">>", text, "\n<<", m.raw_text[:160].replace("\n", " | "))
        await m.click(text="Отправить")
        m = await last(c)
        print("<<", m.raw_text[:160].replace("\n", " | "))
    await asyncio.wait_for(listener, 15)
    print("SSE:", got)
    r = await web.get(BASE + "/")
    print("в списке:", "Тест Е2Е" in r.text)
asyncio.run(main())
