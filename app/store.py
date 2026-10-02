"""Хранилище: один SQLite-файл. Все функции синхронные и короткие — для объёма агентства хватает."""
import sqlite3
from datetime import datetime, timezone

SOURCES = {"bot": "Бот", "telegram": "Личка TG", "manual": "Вручную"}
STATUSES = {"new": "Новый", "work": "В работе", "won": "Сделка", "lost": "Отказ"}
CLOSED = ("won", "lost")
TAG_COLORS = ["indigo", "teal", "amber", "rose", "sky", "violet", "lime", "slate"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    contact TEXT NOT NULL DEFAULT '',
    request TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    tg_user_id INTEGER,
    tg_username TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS leads_tg ON leads(tg_user_id, source, status);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lead_tags (
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (lead_id, tag_id)
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""

_db: sqlite3.Connection | None = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init(path: str) -> None:
    global _db
    _db = sqlite3.connect(path, check_same_thread=False)
    _db.row_factory = sqlite3.Row
    # SQLite lower() не знает кириллицу — поиск через питоновский casefold
    _db.create_function("fold", 1, lambda s: (s or "").casefold(), deterministic=True)
    _db.execute("PRAGMA journal_mode=WAL")
    _db.execute("PRAGMA foreign_keys=ON")
    _db.executescript(SCHEMA)


def db() -> sqlite3.Connection:
    assert _db is not None, "store.init() не вызван"
    return _db


# ---------- лиды ----------

def create_lead(name, contact="", request="", source="manual", *, tg_user_id=None,
                tg_username=None, tags=(), message=None) -> int:
    ts = now()
    with db():
        cur = db().execute(
            "INSERT INTO leads(name, contact, request, source, tg_user_id, tg_username, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (name.strip()[:200], contact.strip()[:200], request.strip()[:4000], source,
             tg_user_id, tg_username, ts, ts))
        lead_id = cur.lastrowid
        if message:
            db().execute("INSERT INTO messages(lead_id, text, created_at) VALUES (?,?,?)",
                         (lead_id, message[:4000], ts))
    for t in tags:
        add_tag(lead_id, t)
    return lead_id


def add_message(lead_id: int, text: str) -> None:
    ts = now()
    with db():
        db().execute("INSERT INTO messages(lead_id, text, created_at) VALUES (?,?,?)",
                     (lead_id, text[:4000], ts))
        db().execute("UPDATE leads SET updated_at=? WHERE id=?", (ts, lead_id))


def find_open_tg_lead(tg_user_id: int):
    return db().execute(
        "SELECT * FROM leads WHERE tg_user_id=? AND source='telegram' AND status NOT IN (?,?)"
        " ORDER BY id DESC LIMIT 1", (tg_user_id, *CLOSED)).fetchone()


def recent_bot_leads(tg_user_id: int, hours: int = 1) -> int:
    since = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - hours * 3600, timezone.utc)
    return db().execute("SELECT count(*) FROM leads WHERE tg_user_id=? AND source='bot' AND created_at>=?",
                        (tg_user_id, since.isoformat(timespec="seconds"))).fetchone()[0]


def get_lead(lead_id: int) -> dict | None:
    row = db().execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        return None
    lead = dict(row)
    lead["tags"] = lead_tags(lead_id)
    lead["messages"] = [dict(m) for m in db().execute(
        "SELECT * FROM messages WHERE lead_id=? ORDER BY id", (lead_id,))]
    return lead


def lead_tags(lead_id: int) -> list[dict]:
    return [dict(r) for r in db().execute(
        "SELECT t.* FROM tags t JOIN lead_tags lt ON lt.tag_id=t.id WHERE lt.lead_id=? ORDER BY t.name",
        (lead_id,))]


def list_leads(tag: int | None = None, source: str | None = None, status: str | None = None,
               q: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM leads WHERE 1=1", []
    if tag:
        sql += " AND id IN (SELECT lead_id FROM lead_tags WHERE tag_id=?)"
        args.append(tag)
    if source:
        sql += " AND source=?"
        args.append(source)
    if status:
        sql += " AND status=?"
        args.append(status)
    if q:
        sql += (" AND (instr(fold(name), ?) OR instr(fold(contact), ?) OR instr(fold(request), ?)"
                " OR id IN (SELECT lead_id FROM messages WHERE instr(fold(text), ?)))")
        args += [q.casefold()] * 4
    rows = [dict(r) for r in db().execute(sql + " ORDER BY updated_at DESC, id DESC", args)]
    for r in rows:
        r["tags"] = lead_tags(r["id"])
    return rows


EDITABLE = {"name", "contact", "request", "status"}


def update_lead(lead_id: int, **fields) -> None:
    fields = {k: v.strip() for k, v in fields.items() if k in EDITABLE and v is not None}
    if fields.get("status") and fields["status"] not in STATUSES:
        raise ValueError("bad status")
    if "name" in fields and not fields["name"]:
        raise ValueError("empty name")
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with db():
        db().execute(f"UPDATE leads SET {sets}, updated_at=? WHERE id=?",
                     (*fields.values(), now(), lead_id))


def delete_lead(lead_id: int) -> None:
    with db():
        db().execute("DELETE FROM leads WHERE id=?", (lead_id,))


def counts() -> dict:
    c = {"total": db().execute("SELECT count(*) FROM leads").fetchone()[0]}
    for col in ("source", "status"):
        c[col] = {r[0]: r[1] for r in db().execute(f"SELECT {col}, count(*) FROM leads GROUP BY {col}")}
    return c


# ---------- теги ----------

def all_tags() -> list[dict]:
    return [dict(r) for r in db().execute(
        "SELECT t.*, count(lt.lead_id) AS n FROM tags t LEFT JOIN lead_tags lt ON lt.tag_id=t.id"
        " GROUP BY t.id ORDER BY n DESC, t.name")]


def get_or_create_tag(name: str) -> int | None:
    name = " ".join(name.split()).lstrip("#")[:40]
    if not name:
        return None
    key = name.casefold()
    row = db().execute("SELECT id FROM tags WHERE name_key=?", (key,)).fetchone()
    if row:
        return row["id"]
    n = db().execute("SELECT count(*) FROM tags").fetchone()[0]
    with db():
        return db().execute("INSERT INTO tags(name, name_key, color) VALUES (?,?,?)",
                            (name, key, TAG_COLORS[n % len(TAG_COLORS)])).lastrowid


def add_tag(lead_id: int, name: str) -> int | None:
    tag_id = get_or_create_tag(name)
    if tag_id:
        with db():
            db().execute("INSERT OR IGNORE INTO lead_tags(lead_id, tag_id) VALUES (?,?)", (lead_id, tag_id))
    return tag_id


def remove_tag(lead_id: int, tag_id: int) -> None:
    with db():
        db().execute("DELETE FROM lead_tags WHERE lead_id=? AND tag_id=?", (lead_id, tag_id))


def rename_tag(tag_id: int, name: str) -> None:
    name = " ".join(name.split()).lstrip("#")[:40]
    if not name:
        raise ValueError("empty tag")
    try:
        with db():
            db().execute("UPDATE tags SET name=?, name_key=? WHERE id=?", (name, name.casefold(), tag_id))
    except sqlite3.IntegrityError:
        raise ValueError("tag exists")


def delete_tag(tag_id: int) -> None:
    with db():
        db().execute("DELETE FROM tags WHERE id=?", (tag_id,))


# ---------- настройки ----------

def get_setting(key: str, default=None):
    row = db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value) -> None:
    with db():
        if value is None:
            db().execute("DELETE FROM settings WHERE key=?", (key,))
        else:
            db().execute("INSERT INTO settings(key, value) VALUES (?,?)"
                         " ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
