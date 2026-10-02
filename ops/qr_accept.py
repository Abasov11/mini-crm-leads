"""Распознать QR со скриншота и подтвердить вход основной сессией аккаунта (как «Подключить устройство»)."""
import asyncio, base64, sys
import zxingcpp
from PIL import Image
sys.path.insert(0, "ops"); from salat import acc, sess, TelegramClient, StringSession
from telethon import functions
url = zxingcpp.read_barcodes(Image.open(sys.argv[1]))[0].text
assert url.startswith("tg://login?token="), url[:20]
tok = url.split("token=", 1)[1]
token = base64.urlsafe_b64decode(tok + "=" * (-len(tok) % 4))
async def main():
    async with TelegramClient(StringSession(sess), acc["api_id"], acc["api_hash"]) as c:
        await c(functions.auth.AcceptLoginTokenRequest(token=token))
asyncio.run(main())
print("OK   QR распознан и подтверждён")
