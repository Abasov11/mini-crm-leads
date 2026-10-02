from types import SimpleNamespace

from app import tg_account


def test_tags_case_insensitive_and_counts(db):
    a = db.create_lead("Анна", "@anna", "Сайт", "manual", tags=["Сайт", "срочно"])
    b = db.create_lead("Борис", "", "Лендинг", "bot", tags=["САЙТ", "#сайт"])
    tags = {t["name"]: t["n"] for t in db.all_tags()}
    assert tags == {"Сайт": 2, "срочно": 1}
    sid = db.get_or_create_tag("сайт")
    assert {l["id"] for l in db.list_leads(tag=sid)} == {a, b}
    db.remove_tag(a, sid)
    assert [l["id"] for l in db.list_leads(tag=sid)] == [b]


def test_filters_combine_and_cyrillic_search(db):
    db.create_lead("Анна", "+7 700", "Нужен ЛЕНДИНГ", "bot")
    db.create_lead("Борис", "", "Реклама", "manual")
    assert [l["name"] for l in db.list_leads(q="лендинг")] == ["Анна"]
    assert [l["name"] for l in db.list_leads(source="manual")] == ["Борис"]
    assert db.list_leads(source="bot", q="реклама") == []


def test_status_validation(db):
    i = db.create_lead("X")
    db.update_lead(i, status="won")
    assert db.get_lead(i)["status"] == "won"
    import pytest
    with pytest.raises(ValueError):
        db.update_lead(i, status="hacked")
    with pytest.raises(ValueError):
        db.update_lead(i, name="  ")


def test_rename_tag_conflict(db):
    db.create_lead("X", tags=["a", "b"])
    import pytest
    with pytest.raises(ValueError):
        db.rename_tag(db.get_or_create_tag("a"), "B")


def _user(uid=5, **kw):
    base = dict(id=uid, first_name="Ия", last_name=None, username="iya", phone=None, bot=False,
                is_self=False, deleted=False)
    base.update(kw)
    u = tg_account.User(id=uid)  # настоящий тип, чтобы isinstance сработал
    for k, v in base.items():
        setattr(u, k, v)
    return u


def test_tg_ingest_groups_open_lead(db):
    u = _user()
    l1, new1 = tg_account.ingest(u, "Здравствуйте")
    l2, new2 = tg_account.ingest(u, "Нужен сайт")
    assert new1 and not new2 and l1 == l2
    lead = db.get_lead(l1)
    assert [m["text"] for m in lead["messages"]] == ["Здравствуйте", "Нужен сайт"]
    assert lead["contact"] == "@iya" and lead["source"] == "telegram"
    # закрытый лид не дописывается — новое обращение = новый лид
    db.update_lead(l1, status="lost")
    l3, new3 = tg_account.ingest(u, "Снова я")
    assert new3 and l3 != l1


def test_tg_ingest_does_not_glue_bot_leads(db):
    u = _user()
    bot_lead = db.create_lead("Ия", "@iya", "из бота", "bot", tg_user_id=u.id)
    lead_id, new = tg_account.ingest(u, "привет")
    assert new and lead_id != bot_lead


def test_tg_ignore_rules(db):
    assert tg_account.should_ignore(_user(bot=True), False)
    assert tg_account.should_ignore(_user(uid=777000), False)
    assert tg_account.should_ignore(_user(is_self=True), False)
    assert tg_account.should_ignore(_user(), True)          # контакт, фильтр включён
    db.set_setting("tg_skip_contacts", "0")
    assert not tg_account.should_ignore(_user(), True)
    assert not tg_account.should_ignore(_user(), False)
    assert tg_account.should_ignore(SimpleNamespace(id=1), False)  # канал/чат, не User


def test_describe_sender_fallbacks(db):
    assert tg_account.describe_sender(_user(username=None, phone="7700")) == ("Ия", "+7700")
    assert tg_account.describe_sender(_user(username=None, first_name=None)) == ("id5", "tg id 5")


def test_describe_sender_meaningless_name(db):
    assert tg_account.describe_sender(_user(first_name=".")) == ("iya", "@iya")
