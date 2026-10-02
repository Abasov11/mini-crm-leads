import os
import sys
from pathlib import Path

os.environ["DISABLE_TELEGRAM"] = "1"
os.environ["PUBLIC_URL"] = "http://testserver"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402


@pytest.fixture
def db(tmp_path):
    from app import store
    store.init(str(tmp_path / "t.db"))
    return store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "w.db"))
    from fastapi.testclient import TestClient
    from app import config, main
    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "w.db"))
    with TestClient(main.app, headers={"origin": "http://testserver"}) as c:
        yield c


def login(c, user="demo"):
    from app.config import USERS
    r = c.post("/login", data={"username": user, "password": USERS[user][1]}, follow_redirects=False)
    assert r.status_code == 303
