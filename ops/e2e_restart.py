"""Живой e2e: /help не становится заявкой; анкета переживает рестарт сервиса посередине."""
import asyncio, subprocess, sys, time
sys.path.insert(0, "ops"); from salat import acc, sess, TelegramClient, StringSession
BOT = "minicrm_agency_leads_bot"
async def say(c, t, wait=2.5):
    await c.send_message(BOT, t); await asyncio.sleep(wait)
    m = (await c.get_messages(BOT, limit=1))[0]; print(">>", t, "\n<<", m.raw_text[:120].replace("\n", " | ")); return m
async def main():
    async with TelegramClient(StringSession(sess), acc["api_id"], acc["api_hash"]) as c:
        await say(c, "/cancel")
        await say(c, "/help")
        await say(c, "/start"); await say(c, "Рестарт Тест")
        subprocess.run(["sudo", "systemctl", "restart", "mini-crm"], check=True); print("-- сервис перезапущен --")
        await asyncio.sleep(10)
        await say(c, "@SalatMalatt", 4)
        m = await say(c, "Проверка, что анкета пережила рестарт")
        await m.click(text="Отправить"); await asyncio.sleep(2.5)
        print("<<", (await c.get_messages(BOT, limit=1))[0].raw_text[:80])
asyncio.run(main())
