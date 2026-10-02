"""Точка входа: веб, бот и подключённый аккаунт в одном процессе."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from . import store, tg_account
from .config import DB_PATH, DISABLE_TELEGRAM
from .web import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app):
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    store.init(DB_PATH)
    tasks = []
    if not DISABLE_TELEGRAM:
        from .bot import build, notifier
        bot, dp = build()
        tasks.append(asyncio.create_task(notifier(bot)))
        # polling сам переподключается при сетевых ошибках
        tasks.append(asyncio.create_task(dp.start_polling(bot, handle_signals=False)))
        tasks.append(asyncio.create_task(tg_account.start()))
    yield
    for t in tasks:
        t.cancel()
    await tg_account.stop()
    if not DISABLE_TELEGRAM:
        await bot.session.close()


app = create_app(lifespan)
