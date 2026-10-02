"""Демо-наполнение: 10 заявок, похожих на реальные. Контакты вымышленные (+7 9xx 000-…, example.com),
ссылок на чужие Telegram-аккаунты нет (tg_username пустой)."""
import sqlite3, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, "."); from app import store

store.init("data/crm.db")
db = store.db()
with db:
    db.execute("DELETE FROM leads"); db.execute("DELETE FROM tags")
    db.execute("DELETE FROM settings WHERE key LIKE 'fsm:%'")
now = datetime.now(timezone.utc).replace(microsecond=0)
ago = lambda h: (now - timedelta(hours=h)).isoformat()

LEADS = [
    # (часов назад, имя, контакт, запрос, источник, статус, теги, сообщения [(часов назад, текст)])
    (78, "Ирина Соколова", "+7 916 000-41-27", "Нужен сайт для стоматологии: 5-6 страниц, онлайн-запись, до конца месяца",
     "bot", "won", ["сайт", "медицина"], None),
    (70, "Дмитрий", "+7 903 000-18-55", "", "telegram", "work", ["реклама", "B2B"],
     [(70, "Добрый день! Вы делаете контекстную рекламу?"),
      (69.9, "У нас оптовые поставки упаковки, Москва и область. Бюджет около 150 тысяч в месяц"),
      (52, "Скинул доступы к Метрике, посмотрите, пожалуйста")]),
    (60, "Студия йоги «Прана»", "prana.studio@example.com", "Ведение инстаграма и телеграм-канала, 12 постов в месяц плюс сторис",
     "manual", "work", ["SMM"], [(60, "Звонок с сайта. Хотят начать с пробного месяца, просили КП до пятницы")]),
    (49, "Алексей Морозов", "alexey.morozov@example.com", "Лендинг под запуск онлайн-курса по 3D, старт продаж через 2 недели",
     "bot", "new", ["лендинг", "срочно"], None),
    (40, "Наталья", "+7 921 000-63-09", "", "telegram", "lost", ["сайт"],
     [(40, "Здравствуйте, сколько стоит сайт-визитка?"),
      (39.5, "Поняла, спасибо, пока дорого. Вернусь весной")]),
    (30, "ООО «СеверСтрой»", "zakupki@example.com", "Тендер на редизайн корпоративного сайта и каталога продукции. Нужна оценка сроков и стоимости",
     "manual", "new", ["сайт", "B2B", "брендинг"], [(30, "Пришло письмом на общую почту, переслал в CRM")]),
    (22, "Марина Ким", "+7 917 000-25-84", "Логотип и фирменный стиль для кофейни, открытие в ноябре",
     "bot", "work", ["брендинг"], None),
    (14, "Артём", "+7 999 000-71-46", "", "telegram", "new", ["реклама", "срочно"],
     [(14, "Привет! Горит запуск, нужна таргетированная реклама ВКонтакте уже на этой неделе"),
      (13.8, "Магазин кроссовок, есть сайт и каталог"),
      (13.7, "Можно сегодня созвониться?")]),
    (6, "Елена Викторовна", "+7 912 000-38-90", "Повторно: доработать форму заявки на сайте, который вы делали в прошлом году",
     "bot", "new", ["сайт", "повторный"], None),
    (1.5, "Кирилл", "+7 905 000-92-13", "Нужен чат-бот в Telegram для записи в барбершоп",
     "bot", "new", ["бот"], None),
]

for h, name, contact, req, src, status, tags, msgs in LEADS:
    if src == "telegram" and not req:
        req = msgs[0][1]
    lid = store.create_lead(name, contact, req, src, tags=tags)
    first = msgs or ([(h, req)] if src == "bot" else [])
    last = h
    with db:
        db.execute("DELETE FROM messages WHERE lead_id=?", (lid,))
        for mh, text in first:
            db.execute("INSERT INTO messages(lead_id, text, created_at) VALUES (?,?,?)", (lid, text, ago(mh)))
            last = min(last, mh)
        db.execute("UPDATE leads SET status=?, created_at=?, updated_at=? WHERE id=?", (status, ago(h), ago(last), lid))
print("leads:", db.execute("SELECT count(*) FROM leads").fetchone()[0], "tags:", [t["name"] for t in store.all_tags()])
