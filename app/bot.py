"""Бот-анкета (п.1): имя → контакт → запрос → подтверждение → лид в CRM."""
import asyncio
import html
import json
import logging
import secrets

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                           Message, ReplyKeyboardMarkup, ReplyKeyboardRemove)

from . import events, store

router = Router()
LEADS_PER_HOUR = 5  # защита от засорения CRM из публичного бота


class SQLiteStorage(BaseStorage):
    """Состояние анкеты в той же базе: рестарт сервиса не сбрасывает человека на середине."""

    @staticmethod
    def _k(key: StorageKey) -> str:
        return f"fsm:{key.chat_id}:{key.user_id}"

    async def set_state(self, key, state=None):
        st = state.state if isinstance(state, State) else state
        store.set_setting(self._k(key) + ":state", st)

    async def get_state(self, key):
        return store.get_setting(self._k(key) + ":state")

    async def set_data(self, key, data):
        store.set_setting(self._k(key) + ":data", json.dumps(data, ensure_ascii=False) if data else None)

    async def get_data(self, key):
        raw = store.get_setting(self._k(key) + ":data")
        return json.loads(raw) if raw else {}

    async def close(self):
        pass


class Form(StatesGroup):
    name = State()
    contact = State()
    request = State()
    confirm = State()


def _kb(*rows) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[list(r) for r in rows], resize_keyboard=True, one_time_keyboard=True)


def _tg_handle(username: str | None) -> str:
    return f"Пишите сюда в Telegram @{username}" if username else ""


async def ask_name(m: Message, state: FSMContext):
    await state.set_state(Form.name)
    first = (m.from_user.full_name or "").strip()
    await m.answer("Как к вам обращаться?",
                   reply_markup=_kb([KeyboardButton(text=first)]) if first else ReplyKeyboardRemove())


async def ask_contact(m: Message, state: FSMContext):
    await state.set_state(Form.contact)
    rows = [[KeyboardButton(text="Поделиться номером", request_contact=True)]]
    if m.from_user.username:
        rows.append([KeyboardButton(text=_tg_handle(m.from_user.username))])
    await m.answer("Как с вами удобнее связаться? Нажмите кнопку или напишите телефон, почту или ник.",
                   reply_markup=_kb(*rows))


async def ask_request(m: Message, state: FSMContext):
    await state.set_state(Form.request)
    await m.answer("Коротко опишите задачу: что нужно сделать и к какому сроку.", reply_markup=ReplyKeyboardRemove())


async def ask_confirm(m: Message, state: FSMContext):
    await state.set_state(Form.confirm)
    d = await state.get_data()
    text = (f"Проверьте заявку:\n\n<b>Имя:</b> {html.escape(d['name'])}\n<b>Контакт:</b> {html.escape(d['contact'])}\n"
            f"<b>Запрос:</b> {html.escape(d['request'])}")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Отправить", callback_data="send"),
        InlineKeyboardButton(text="Заполнить заново", callback_data="restart")]])
    await m.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(CommandStart(deep_link=True, magic=F.args.startswith("m_")))
async def manager_subscribe(m: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    if command.args[2:] != notify_token():
        return await m.answer("Ссылка для уведомлений устарела. Возьмите новую в настройках CRM.")
    chats = notify_chats()
    if m.chat.id not in chats:
        store.set_setting("notify_chats", json.dumps(chats + [m.chat.id]))
    await m.answer("Уведомления включены: сюда будут приходить новые заявки из CRM. Отключить: /stop",
                   reply_markup=ReplyKeyboardRemove())


@router.message(Command("stop"))
async def manager_unsubscribe(m: Message, state: FSMContext):
    chats = notify_chats()
    if m.chat.id in chats:
        store.set_setting("notify_chats", json.dumps([c for c in chats if c != m.chat.id]))
        return await m.answer("Уведомления отключены.")
    await m.answer("Уведомления и так не включены. Чтобы оставить заявку, нажмите /start.")


@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Здравствуйте! Здесь можно оставить заявку для агентства. Три коротких вопроса, "
                   "и менеджер свяжется с вами. Прервать можно командой /cancel.")
    await ask_name(m, state)


@router.message(Command("cancel"))
async def cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Хорошо, заявку не отправляю. Начать заново: /start.", reply_markup=ReplyKeyboardRemove())


@router.message(StateFilter(None), F.text.startswith("/"))
async def unknown_command(m: Message):
    await m.answer("Чтобы оставить заявку, нажмите /start или просто опишите задачу сообщением.")


@router.message(StateFilter(None), F.text)
async def first_message(m: Message, state: FSMContext):
    # Человек сразу написал задачу, без /start — не теряем её, сохраним как запрос
    await state.update_data(request=m.text.strip()[:4000])
    await m.answer("Здравствуйте! Записал вашу задачу. Остались два вопроса, и заявка уйдёт менеджеру.")
    await ask_name(m, state)


@router.message(Form.name, F.text)
async def got_name(m: Message, state: FSMContext):
    name = m.text.strip()
    if not 1 <= len(name) <= 100:
        return await m.answer("Напишите, пожалуйста, имя короче, до 100 символов.")
    await state.update_data(name=name)
    await ask_contact(m, state)


def is_own_contact(contact, user) -> bool:
    # кнопка «Поделиться номером» всегда шлёт свой контакт с user_id; пересланная чужая карточка — нет
    return contact.user_id is not None and contact.user_id == user.id


@router.message(Form.contact, F.contact)
async def got_phone(m: Message, state: FSMContext):
    if not is_own_contact(m.contact, m.from_user):
        return await m.answer("Похоже, это чужой контакт. Нажмите кнопку «Поделиться номером» "
                              "или напишите свой телефон текстом.")
    await _save_contact(m, state, "+" + m.contact.phone_number.lstrip("+"))


@router.message(Form.contact, F.text)
async def got_contact_text(m: Message, state: FSMContext):
    text = m.text.strip()
    if m.from_user.username and text == _tg_handle(m.from_user.username):
        text = "@" + m.from_user.username
    if len(text) < 3:
        return await m.answer("Не похоже на контакт. Напишите телефон, почту или ник в Telegram.")
    await _save_contact(m, state, text[:200])


async def _save_contact(m: Message, state: FSMContext, contact: str):
    await state.update_data(contact=contact)
    if (await state.get_data()).get("request"):
        return await ask_confirm(m, state)
    await ask_request(m, state)


@router.message(Form.request, F.text)
async def got_request(m: Message, state: FSMContext):
    if len(m.text.strip()) < 3:
        return await m.answer("Напишите чуть подробнее, что нужно сделать.")
    await state.update_data(request=m.text.strip()[:4000])
    await ask_confirm(m, state)


@router.callback_query(Form.confirm, F.data == "send")
async def send(c: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    u = c.from_user
    if store.recent_bot_leads(u.id, hours=1) >= LEADS_PER_HOUR:
        await c.answer("Заявок за последний час уже много. Менеджер видит предыдущие, напишите чуть позже.",
                       show_alert=True)
        return
    await state.clear()
    lead_id = store.create_lead(d["name"], d["contact"], d["request"], "bot",
                                tg_user_id=u.id, tg_username=u.username, message=d["request"])
    events.publish("new", lead_id)
    await c.message.edit_reply_markup(reply_markup=None)
    await c.message.answer(f"Готово, заявка №{lead_id} принята. Менеджер свяжется с вами в ближайшее время.\n\n"
                           "Если появится ещё одна задача, просто напишите её сюда.")
    await c.answer()


@router.callback_query(Form.confirm, F.data == "restart")
async def restart(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_reply_markup(reply_markup=None)
    await c.answer()
    # ask_name() не подходит: у c.message отправитель — сам бот, имя берём из c.from_user
    await state.set_state(Form.name)
    first = (c.from_user.full_name or "").strip()
    await c.message.answer("Начнём заново. Как к вам обращаться?",
                           reply_markup=_kb([KeyboardButton(text=first)]) if first else ReplyKeyboardRemove())


@router.callback_query()
async def stale_button(c: CallbackQuery):
    await c.answer("Эта заявка уже отправлена или отменена. Новая заявка: /start.", show_alert=True)


@router.message(Form.confirm)
async def confirm_hint(m: Message):
    await m.answer("Нажмите «Отправить» или «Заполнить заново» под заявкой выше.")


@router.message()
async def wrong_type(m: Message):
    await m.answer("Пока я понимаю только текст. Ответьте, пожалуйста, текстом или кнопкой.")


# ---------- уведомления менеджерам ----------

log = logging.getLogger("bot")


def notify_token() -> str:
    tok = store.get_setting("notify_token")
    if not tok:
        tok = secrets.token_urlsafe(12).replace("-", "x").replace("_", "y")
        store.set_setting("notify_token", tok)
    return tok


def notify_chats() -> list[int]:
    return json.loads(store.get_setting("notify_chats") or "[]")


def notify_text(lead: dict) -> str:
    req = lead["request"] if len(lead["request"]) <= 300 else lead["request"][:300] + "…"
    lines = [f"<b>Новая заявка №{lead['id']}</b> · {store.SOURCES[lead['source']]}",
             html.escape(lead["name"]) + (f", {html.escape(lead['contact'])}" if lead["contact"] else "")]
    if req:
        lines.append("\n" + html.escape(req))
    return "\n".join(lines)


async def notifier(bot: Bot) -> None:
    """Слушает шину событий и шлёт менеджерам каждую новую заявку из любого канала."""
    from .config import PUBLIC_URL
    q = events.subscribe()
    while True:
        ev = await q.get()
        if ev["kind"] != "new":
            continue
        lead = store.get_lead(ev["lead_id"])
        if not lead:
            continue
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Открыть в CRM", url=f"{PUBLIC_URL}/leads/{lead['id']}")]])
        for chat in notify_chats():
            try:
                await bot.send_message(chat, notify_text(lead), parse_mode="HTML", reply_markup=kb)
            except Exception:
                log.exception("notify %s failed", chat)
            await asyncio.sleep(0.05)


def build() -> tuple[Bot, Dispatcher]:
    from .config import BOT_TOKEN
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=SQLiteStorage())
    dp.include_router(router)
    return bot, dp
