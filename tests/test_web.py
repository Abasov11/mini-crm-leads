from conftest import login


def test_requires_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    assert client.get("/doc").status_code == 200
    assert client.get("/health").json()["ok"]


def test_bad_password_and_open_redirect(client):
    r = client.post("/login", data={"username": "demo", "password": "x"})
    assert "Неверный" in r.text
    from app.config import USERS
    r = client.post("/login", data={"username": "demo", "password": USERS["demo"][1], "next": "//evil.com"},
                    follow_redirects=False)
    assert r.headers["location"] == "/"


def test_manual_lead_tags_and_filter(client):
    login(client)
    r = client.post("/leads", data={"name": "Анна", "contact": "+7 700", "req": "Сайт", "tags": "сайт, B2B"},
                    follow_redirects=False)
    assert r.status_code == 303
    lead_url = r.headers["location"]
    page = client.get(lead_url).text
    assert "#сайт" in page and "#B2B" in page
    client.post("/leads", data={"name": "Борис", "tags": "реклама"})
    from app import store
    sid = store.get_or_create_tag("сайт")
    lst = client.get(f"/?tag={sid}").text
    assert "Анна" in lst and "Борис" not in lst
    # снять тег — лид пропадает из фильтра
    lead_id = int(lead_url.rsplit("/", 1)[1])
    client.post(f"/leads/{lead_id}/tags/{sid}/delete")
    assert "Анна" not in client.get(f"/?tag={sid}").text
    # добавить тег из карточки
    r = client.post(f"/leads/{lead_id}/tags", data={"name": "срочно"})
    assert "#срочно" in r.text


def test_manual_lead_requires_name(client):
    login(client)
    r = client.post("/leads", data={"name": " ", "req": "x"})
    assert "Укажите имя" in r.text


def test_update_and_status(client):
    login(client)
    r = client.post("/leads", data={"name": "Анна"}, follow_redirects=False)
    lid = r.headers["location"].rsplit("/", 1)[1]
    assert client.post(f"/leads/{lid}", data={"status": "won", "contact": "@a"}).status_code == 200
    from app import store
    lead = store.get_lead(int(lid))
    assert lead["status"] == "won" and lead["contact"] == "@a"
    assert client.post(f"/leads/{lid}", data={"name": ""}).status_code == 422


def test_csrf_blocks_foreign_origin(client):
    login(client)
    r = client.post("/leads", data={"name": "X"}, headers={"origin": "https://evil.com"})
    assert r.status_code == 403


def test_demo_cannot_touch_telegram(client):
    login(client, "demo")
    assert client.post("/settings/tg/disconnect").status_code == 403
    assert client.post("/settings/tg/connect").status_code == 403
    assert client.get("/settings").status_code == 200


def test_escaping(client):
    login(client)
    client.post("/leads", data={"name": "<script>alert(1)</script>"})
    assert "<script>alert(1)" not in client.get("/").text


def test_open_redirect_backslash(client):
    from app.config import USERS
    r = client.post("/login", data={"username": "demo", "password": USERS["demo"][1], "next": "/\\evil.com"},
                    follow_redirects=False)
    assert r.headers["location"] == "/"


def test_demo_cannot_delete(client):
    login(client, "demo")
    r = client.post("/leads", data={"name": "Анна", "tags": "x"}, follow_redirects=False)
    lid = r.headers["location"].rsplit("/", 1)[1]
    assert "Удалить лида" not in client.get(f"/leads/{lid}").text
    assert client.post(f"/leads/{lid}/delete").status_code == 403
    from app import store
    assert client.post(f"/tags/{store.get_or_create_tag('x')}/delete").status_code == 403
    assert store.get_lead(int(lid))


def test_admin_can_delete(client):
    login(client, "admin")
    r = client.post("/leads", data={"name": "Анна"}, follow_redirects=False)
    lid = r.headers["location"].rsplit("/", 1)[1]
    assert client.post(f"/leads/{lid}/delete", follow_redirects=False).status_code == 303
    from app import store
    assert store.get_lead(int(lid)) is None


def test_settings_shows_notify_link(client):
    login(client)
    r = client.get("/settings").text
    assert "?start=m_" in r and "Получать уведомления" in r
