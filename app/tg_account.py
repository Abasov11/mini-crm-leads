"""Подключённый Telegram-аккаунт (п.2): входящие в личку становятся лидами.

Подключение — из настроек CRM по QR-коду (с паролем 2FA, если он включён).
Сессия хранится в settings, после рестарта процесса аккаунт поднимается сам.
"""
import asyncio
import logging

from telethon import TelegramClient, events as tg_events
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession
from telethon.tl.types import User

from . import events, store
from .config import TG_API_HASH, TG_API_ID

log = logging.getLogger("tg_account")
SERVICE_IDS = {777000, 42777}  # служебные уведомления Telegram

client: TelegramClient | None = None
# состояние подключения для страницы настроек
status = {"state": "idle", "qr_url": None, "error": None}
_login_client: TelegramClient | None = None
_login_task: asyncio.Task | None = None
_seen: set[tuple[int, int]] = set()


def connected_as() -> str | None:
    return store.get_setting("tg_me")


def skip_contacts() -> bool:
    return store.get_setting("tg_skip_contacts", "1") == "1"


def describe_sender(u: User) -> tuple[str, str]:
    name = " ".join(p for p in (u.first_name, u.last_name) if p).strip()
    if not any(ch.isalnum() for ch in name):  # имя из точки или эмодзи ничего не говорит менеджеру
        name = u.username or f"id{u.id}"
    if u.username:
        contact = "@" + u.username
    elif u.phone:
        contact = "+" + u.phone.lstrip("+")
    else:
        contact = f"tg id {u.id}"
    return name, contact


def should_ignore(u, is_contact: bool) -> bool:
    if not isinstance(u, User) or u.bot or u.is_self or u.id in SERVICE_IDS or u.deleted:
        return True
    return is_contact and skip_contacts()


def message_text(msg) -> str:
    text = (msg.raw_text or "").strip()
    if msg.media and not text:
        return "[вложение без текста]"
    if msg.media:
        return text + "\n[есть вложение]"
    return text


def ingest(u: User, text: str) -> tuple[int, bool]:
    """Склейка: открытый лид из Telegram от этого человека получает сообщение в историю,
    иначе создаётся новый. Возвращает (lead_id, создан_ли_новый)."""
    lead = store.find_open_tg_lead(u.id)
    if lead:
        store.add_message(lead["id"], text)
        return lead["id"], False
    name, contact = describe_sender(u)
    lead_id = store.create_lead(name, contact, text, "telegram", tg_user_id=u.id,
                                tg_username=u.username, message=text)
    return lead_id, True


async def _on_message(e):
    key = (e.chat_id, e.id)
    if key in _seen:
        return
    _seen.add(key)
    u = await e.get_sender()
    if should_ignore(u, bool(getattr(u, "contact", False))):
        log.info("tg skip from %s (contact=%s bot=%s)", getattr(u, "id", "?"), getattr(u, "contact", None),
                 getattr(u, "bot", None))
        return
    lead_id, new = ingest(u, message_text(e.message))
    events.publish("new" if new else "update", lead_id)
    log.info("tg lead %s %s", lead_id, "new" if new else "append")


async def _run(session: str) -> bool:
    global client
    c = TelegramClient(StringSession(session), TG_API_ID, TG_API_HASH, catch_up=True)
    await c.connect()
    if not await c.is_user_authorized():
        await c.disconnect()
        store.set_setting("tg_session", None)
        store.set_setting("tg_me", None)
        status.update(state="error", error="Сессия Telegram больше не действует, подключите заново.")
        return False
    c.add_event_handler(_on_message, tg_events.NewMessage(incoming=True, func=lambda e: e.is_private))
    client = c
    me = await c.get_me()
    name, contact = describe_sender(me)
    store.set_setting("tg_me", contact if name.lstrip("@") == contact.lstrip("@") else f"{name} ({contact})")
    status.update(state="connected", qr_url=None, error=None)
    await c.catch_up()
    return True


async def start() -> None:
    session = store.get_setting("tg_session")
    if session:
        try:
            await _run(session)
        except Exception as ex:  # сеть, бан, что угодно — CRM должна работать и без аккаунта
            log.exception("tg account start failed")
            status.update(state="error", error=f"Не удалось подключиться: {ex}")


async def stop() -> None:
    for c in (client, _login_client):
        if c:
            await c.disconnect()


# ---------- подключение по QR ----------

async def begin_qr() -> None:
    global _login_client, _login_task
    await cancel_login()
    _login_client = TelegramClient(StringSession(), TG_API_ID, TG_API_HASH)
    await _login_client.connect()
    qr = await _login_client.qr_login()
    status.update(state="qr", qr_url=qr.url, error=None)
    _login_task = asyncio.create_task(_wait_qr(qr))


async def _wait_qr(qr) -> None:
    try:
        for _ in range(8):  # QR живёт ~30 с, обновляем его до 4 минут
            try:
                await qr.wait(timeout=30)
                return await _finish_login()
            except asyncio.TimeoutError:
                await qr.recreate()
                status["qr_url"] = qr.url
        status.update(state="idle", qr_url=None, error="QR-код не отсканировали, попробуйте ещё раз.")
        await cancel_login()
    except SessionPasswordNeededError:
        status.update(state="password", qr_url=None, error=None)
    except Exception as ex:
        log.exception("qr login failed")
        status.update(state="idle", qr_url=None, error=f"Ошибка входа: {ex}")
        await cancel_login()


async def submit_password(password: str) -> None:
    try:
        await _login_client.sign_in(password=password)
    except Exception as ex:
        status.update(error=f"Пароль не подошёл: {ex.__class__.__name__}")
        return
    await _finish_login()


async def _finish_login() -> None:
    global _login_client
    session = _login_client.session.save()
    await _login_client.disconnect()
    _login_client = None
    if client:
        await disconnect(log_out=True)
    store.set_setting("tg_session", session)
    await _run(session)


async def cancel_login() -> None:
    global _login_client, _login_task
    if _login_task and not _login_task.done() and _login_task is not asyncio.current_task():
        _login_task.cancel()
    _login_task = None
    if _login_client:
        await _login_client.disconnect()
        _login_client = None
    if status["state"] in ("qr", "password"):
        status.update(state="idle", qr_url=None)


async def disconnect(log_out: bool = True) -> None:
    global client
    if client:
        try:
            if log_out:
                await client.log_out()
            else:
                await client.disconnect()
        except Exception:
            log.exception("tg logout")
        client = None
    store.set_setting("tg_session", None)
    store.set_setting("tg_me", None)
    status.update(state="idle", qr_url=None, error=None)
