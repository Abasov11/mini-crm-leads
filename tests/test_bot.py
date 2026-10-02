import asyncio

from aiogram.fsm.storage.base import StorageKey

from app import bot


def test_fsm_storage_survives_new_instance(db):
    key = StorageKey(bot_id=1, chat_id=10, user_id=10)
    s1 = bot.SQLiteStorage()
    asyncio.run(s1.set_state(key, bot.Form.contact))
    asyncio.run(s1.update_data(key, {"name": "Анна"}))
    s2 = bot.SQLiteStorage()  # как после рестарта процесса
    assert asyncio.run(s2.get_state(key)) == "Form:contact"
    assert asyncio.run(s2.get_data(key)) == {"name": "Анна"}
    asyncio.run(s2.set_state(key, None))
    asyncio.run(s2.set_data(key, {}))
    assert asyncio.run(s1.get_state(key)) is None and asyncio.run(s1.get_data(key)) == {}


def test_recent_bot_leads_counts_only_bot_source(db):
    for _ in range(3):
        db.create_lead("A", source="bot", tg_user_id=7)
    db.create_lead("A", source="telegram", tg_user_id=7)
    assert db.recent_bot_leads(7) == 3
    assert db.recent_bot_leads(8) == 0


def test_own_contact_check():
    from types import SimpleNamespace as N
    me = N(id=5)
    assert bot.is_own_contact(N(user_id=5), me)
    assert not bot.is_own_contact(N(user_id=6), me)
    assert not bot.is_own_contact(N(user_id=None), me)


def test_notify_text_escapes_and_trims(db):
    lid = db.create_lead("<b>Анна</b>", "@anna", "x" * 400, "bot")
    text = bot.notify_text(db.get_lead(lid))
    assert "&lt;b&gt;Анна" in text and "Новая заявка №" in text and "Бот" in text
    assert text.endswith("…") and len(text) < 450


def test_notify_token_stable(db):
    t = bot.notify_token()
    assert t == bot.notify_token() and len(t) >= 12 and "_" not in t
