"""Веб-интерфейс CRM: FastAPI + Jinja2 + htmx, живое обновление через SSE."""
import asyncio
import hmac
import json
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo

import segno
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import events, store, tg_account
from .config import DEMO_PASSWORD, PUBLIC_URL, SECRET_KEY, USERS

HERE = Path(__file__).parent
TZ = ZoneInfo("Europe/Moscow")
BOT_USERNAME = "minicrm_agency_leads_bot"

templates = Jinja2Templates(directory=HERE / "templates")
templates.env.globals.update(SOURCES=store.SOURCES, STATUSES=store.STATUSES, BOT_USERNAME=BOT_USERNAME,
                            DEMO_PASSWORD=DEMO_PASSWORD)


def _ago(ts: str) -> str:
    dt = datetime.fromisoformat(ts)
    sec = int((datetime.now(dt.tzinfo) - dt).total_seconds())
    if sec < 60:
        return "только что"
    if sec < 3600:
        return f"{sec // 60} мин назад"
    local = dt.astimezone(TZ)
    if sec < 86400 and local.date() == datetime.now(TZ).date():
        return local.strftime("сегодня %H:%M")
    return local.strftime("%d.%m %H:%M")


templates.env.filters["ago"] = _ago
templates.env.filters["local"] = lambda ts: datetime.fromisoformat(ts).astimezone(TZ).strftime("%d.%m.%Y %H:%M")


def render(request: Request, name: str, **ctx) -> HTMLResponse:
    ctx.setdefault("user", request.session.get("user"))
    return templates.TemplateResponse(request, name, ctx)


# ---------- доступ ----------

class LoginRequired(Exception):
    pass


def current_user(request: Request) -> str:
    user = request.session.get("user")
    if user not in USERS:
        raise LoginRequired()
    return user


def admin_only(user: str = Depends(current_user)) -> str:
    if user != "admin":
        raise HTTPException(403, "Это действие доступно только администратору")
    return user


_attempts: dict[str, deque] = defaultdict(deque)


def _rate_limited(ip: str) -> bool:
    q, now = _attempts[ip], time.monotonic()
    while q and now - q[0] > 600:
        q.popleft()
    return len(q) >= 10


def create_app(lifespan=None) -> FastAPI:
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="crm",
                       max_age=14 * 86400, same_site="lax", https_only=PUBLIC_URL.startswith("https"))
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    @app.middleware("http")
    async def csrf_and_headers(request: Request, call_next):
        # CSRF: любой POST должен прийти с нашей же страницы
        if request.method == "POST":
            origin = request.headers.get("origin") or request.headers.get("referer") or ""
            if urlparse(origin).netloc != request.headers.get("host"):
                return Response("Запрос отклонён: другой источник", status_code=403)
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Content-Security-Policy",
                                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                "script-src 'self'; frame-ancestors 'none'")
        return resp

    @app.exception_handler(LoginRequired)
    async def to_login(request: Request, _):
        if request.headers.get("hx-request"):
            return Response(status_code=204, headers={"HX-Redirect": "/login"})
        return RedirectResponse("/login?next=" + request.url.path, 303)

    # ---------- вход ----------

    @app.get("/login")
    def login_page(request: Request, next: str = "/"):
        return render(request, "login.html", next=next, error=None)

    @app.post("/login")
    def login(request: Request, username: str = Form(""), password: str = Form(""), next: str = Form("/")):
        ip = request.headers.get("x-real-ip") or request.client.host
        if _rate_limited(ip):
            return render(request, "login.html", next=next, error="Слишком много попыток, подождите 10 минут.")
        u = USERS.get(username.strip().lower())
        if not u or not hmac.compare_digest(u[1].encode(), password.encode()):
            _attempts[ip].append(time.monotonic())
            return render(request, "login.html", next=next, error="Неверный логин или пароль.")
        request.session["user"] = u[0]
        return RedirectResponse(next if next.startswith("/") and not next.startswith(("//", "/\\")) and "\\" not in next else "/", 303)

    @app.post("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", 303)

    # ---------- список ----------

    def _filters(tag: str = "", source: str = "", status: str = "", q: str = "") -> dict:
        return {"tag": int(tag) if tag.isdigit() else None,
                "source": source if source in store.SOURCES else None,
                "status": status if status in store.STATUSES else None,
                "q": q.strip() or None}

    def _list_ctx(f: dict) -> dict:
        tags = store.all_tags()
        return {"leads": store.list_leads(**f), "f": f, "tags": tags, "counts": store.counts(),
                "active_tag": next((t for t in tags if t["id"] == f["tag"]), None),
                "qs": lambda **kw: "?" + urlencode({k: v for k, v in {**f, **kw}.items() if v})}

    @app.get("/")
    def leads_page(request: Request, user=Depends(current_user), f=Depends(_filters)):
        return render(request, "leads.html", **_list_ctx(f))

    @app.get("/events")
    async def sse(request: Request, user=Depends(current_user)):
        q = events.subscribe()

        async def stream():
            try:
                yield "retry: 3000\n\n"
                while not await request.is_disconnected():
                    try:
                        ev = await asyncio.wait_for(q.get(), timeout=20)
                        yield f"data: {json.dumps(ev)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
            finally:
                events.unsubscribe(q)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ---------- лид ----------

    @app.get("/leads/new")
    def new_page(request: Request, user=Depends(current_user)):
        return render(request, "new.html", tags=store.all_tags(), error=None, form={})

    @app.post("/leads")
    def create(request: Request, user=Depends(current_user), name: str = Form(""), contact: str = Form(""),
               req: str = Form(""), tags: str = Form("")):
        if not name.strip():
            return render(request, "new.html", tags=store.all_tags(), error="Укажите имя.",
                          form={"name": name, "contact": contact, "req": req, "tags": tags})
        lead_id = store.create_lead(name, contact, req, "manual", tags=[t for t in tags.split(",") if t.strip()],
                                    message=req.strip() or None)
        events.publish("new", lead_id)
        return RedirectResponse(f"/leads/{lead_id}", 303)

    def _lead_or_404(lead_id: int) -> dict:
        lead = store.get_lead(lead_id)
        if not lead:
            raise HTTPException(404, "Лид не найден")
        return lead

    @app.get("/leads/{lead_id}")
    def lead_page(request: Request, lead_id: int, user=Depends(current_user)):
        return render(request, "lead.html", lead=_lead_or_404(lead_id), tags=store.all_tags())

    @app.post("/leads/{lead_id}")
    async def update(request: Request, lead_id: int, user=Depends(current_user)):
        _lead_or_404(lead_id)
        # форму читаем напрямую: Form(None) превращает пустую строку в None, и стёртое поле не сохранилось бы
        form = await request.form()
        try:
            store.update_lead(lead_id, name=form.get("name"), contact=form.get("contact"),
                              request=form.get("req"), status=form.get("status"))
        except ValueError:
            return Response("Имя не может быть пустым", status_code=422)
        events.publish("update", lead_id)
        return render(request, "_saved.html")

    @app.post("/leads/{lead_id}/delete")
    def delete(lead_id: int, user=Depends(admin_only)):
        store.delete_lead(lead_id)
        events.publish("delete", lead_id)
        return RedirectResponse("/", 303)

    @app.post("/leads/{lead_id}/tags")
    def tag_add(request: Request, lead_id: int, user=Depends(current_user), name: str = Form("")):
        lead = _lead_or_404(lead_id)
        for part in name.split(","):
            store.add_tag(lead_id, part)
        events.publish("update", lead_id)
        lead["tags"] = store.lead_tags(lead_id)
        return render(request, "_tags.html", lead=lead, tags=store.all_tags())

    @app.post("/leads/{lead_id}/tags/{tag_id}/delete")
    def tag_remove(request: Request, lead_id: int, tag_id: int, user=Depends(current_user)):
        lead = _lead_or_404(lead_id)
        store.remove_tag(lead_id, tag_id)
        events.publish("update", lead_id)
        lead["tags"] = store.lead_tags(lead_id)
        return render(request, "_tags.html", lead=lead, tags=store.all_tags())

    # ---------- настройки ----------

    def _settings_ctx(**kw):
        qr = tg_account.status.get("qr_url")
        from .bot import notify_chats, notify_token
        return {"notify_link": f"https://t.me/{BOT_USERNAME}?start=m_{notify_token()}",
                "notify_count": len(notify_chats()),
                "tg": tg_account.status, "tg_me": tg_account.connected_as(),
                "skip_contacts": tg_account.skip_contacts(), "tags": store.all_tags(),
                "qr_svg": segno.make(qr, error="m").svg_inline(scale=5, dark="#0f172a", light="#ffffff") if qr else None,
                **kw}

    @app.get("/settings")
    def settings_page(request: Request, user=Depends(current_user)):
        return render(request, "settings.html", **_settings_ctx())

    @app.get("/settings/tg")
    def tg_status(request: Request, user=Depends(current_user)):
        return render(request, "_tg.html", **_settings_ctx())

    @app.post("/settings/tg/connect")
    async def tg_connect(request: Request, user=Depends(admin_only)):
        try:
            await tg_account.begin_qr()
        except Exception as ex:
            tg_account.status.update(state="idle", error=f"Telegram недоступен: {ex}")
        return render(request, "_tg.html", **_settings_ctx())

    @app.post("/settings/tg/password")
    async def tg_password(request: Request, user=Depends(admin_only), password: str = Form("")):
        await tg_account.submit_password(password)
        return render(request, "_tg.html", **_settings_ctx())

    @app.post("/settings/tg/cancel")
    async def tg_cancel(request: Request, user=Depends(admin_only)):
        await tg_account.cancel_login()
        return render(request, "_tg.html", **_settings_ctx())

    @app.post("/settings/tg/disconnect")
    async def tg_disconnect(request: Request, user=Depends(admin_only)):
        await tg_account.disconnect()
        return render(request, "_tg.html", **_settings_ctx())

    @app.post("/settings/tg/contacts")
    def tg_contacts(request: Request, user=Depends(admin_only), skip: str = Form("0")):
        store.set_setting("tg_skip_contacts", "1" if skip == "1" else "0")
        return render(request, "_tg.html", **_settings_ctx())

    @app.post("/tags/{tag_id}/rename")
    def tag_rename(request: Request, tag_id: int, user=Depends(current_user), name: str = Form("")):
        try:
            store.rename_tag(tag_id, name)
            err = None
        except ValueError:
            err = "Такой тег уже есть или имя пустое."
        return render(request, "_tag_admin.html", tags=store.all_tags(), tag_error=err)

    @app.post("/tags/{tag_id}/delete")
    def tag_delete(request: Request, tag_id: int, user=Depends(admin_only)):
        store.delete_tag(tag_id)
        return render(request, "_tag_admin.html", tags=store.all_tags(), tag_error=None)

    # ---------- публичное ----------

    @app.get("/doc")
    def doc(request: Request):
        return render(request, "doc.html")

    @app.get("/health")
    def health():
        return {"ok": True, "leads": store.counts()["total"], "tg_account": tg_account.status["state"]}

    return app
