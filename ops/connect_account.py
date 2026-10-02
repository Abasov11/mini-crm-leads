"""Разовое подключение аккаунта к CRM: новая сессия выдаёт QR-токен, основная сессия аккаунта его подтверждает
(то же самое, что «Настройки → Устройства → Подключить устройство» на телефоне)."""
import asyncio, sqlite3, sys
sys.path.insert(0, "ops"); from salat import acc, sess, TelegramClient, StringSession
from telethon import functions
from telethon.errors import SessionPasswordNeededError
DB = "data/crm.db"

async def main():
    new = TelegramClient(StringSession(), acc["api_id"], acc["api_hash"], device_model="Mini-CRM")
    await new.connect()
    qr = await new.qr_login()
    async with TelegramClient(StringSession(sess), acc["api_id"], acc["api_hash"]) as old:
        await old(functions.auth.AcceptLoginTokenRequest(token=qr.token))
    try:
        await qr.wait(timeout=30)
    except SessionPasswordNeededError:
        print("нужен пароль 2FA — стоп"); return
    me = await new.get_me()
    s = new.session.save()
    await new.disconnect()
    db = sqlite3.connect(DB)
    db.execute("INSERT INTO settings(key,value) VALUES('tg_session',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (s,))
    db.commit()
    print("ok:", me.first_name, me.username, me.id)

asyncio.run(main())
