"""Одноразовые операции от второго аккаунта через его основную сессию (короткое подключение)."""
import asyncio, json, os, sys
from telethon import TelegramClient
from telethon.sessions import StringSession
B = os.environ.get("TG_OPS_DIR", "ops/.local/")  # tg_account.json + tg_session.txt основной сессии
acc = json.load(open(B + "tg_account.json"))
sess = open(B + "tg_session.txt").read().strip()

async def botfather(*msgs):
    async with TelegramClient(StringSession(sess), acc["api_id"], acc["api_hash"]) as c:
        for m in msgs:
            await c.send_message("BotFather", m)
            await asyncio.sleep(2.5)
            r = (await c.get_messages("BotFather", limit=1))[0]
            print(">>", m, "\n<<", r.text, "\n")

if __name__ == "__main__":
    asyncio.run(botfather(*sys.argv[1:]))
