import asyncio, re, sys
sys.path.insert(0, "ops"); from salat import *
async def main():
    async with TelegramClient(StringSession(sess), acc["api_id"], acc["api_hash"]) as c:
        for m in await c.get_messages("BotFather", limit=10):
            t = re.search(r"\d{8,}:[A-Za-z0-9_-]{30,}", m.text or "")
            if t and "minicrm_agency_leads_bot" in m.text: print(t.group(0)); return
asyncio.run(main())
