# Мини-CRM заявок агентства

Тестовое задание: CRM, куда сами собираются лиды из Telegram-бота и из подключенного личного Telegram, плюс ручное добавление и теги.

- Живая версия: https://crm.213-32-66-46.nip.io (вход `demo` / `demo2026`)
- Набросок продукта и разбор: https://crm.213-32-66-46.nip.io/doc
- Бот: [@minicrm_agency_leads_bot](https://t.me/minicrm_agency_leads_bot)
- Проект до кода (архитектура, данные, логика каналов, дизайн, критерии готовности): [DESIGN.md](DESIGN.md)

## Что умеет
- **Бот-анкета**: имя, контакт, задача, сводка перед отправкой. Задача, написанная без /start, не теряется. Анкета переживает перезапуск сервиса. Лимит 5 заявок в час на человека.
- **Подключенный аккаунт** (Telethon, вход по QR из настроек, с 2FA): входящие в личку становятся лидами, повторные сообщения дописываются в открытый лид, контакты, боты и служебные уведомления пропускаются.
- **Ручное добавление**, **теги** со счетчиками и фильтром; фильтры по тегу, источнику, статусу и поиск складываются.
- **Живой список** через SSE, **уведомления менеджеру** в Telegram с кнопкой «Открыть в CRM».
- Роли admin/demo, CSRF по Origin, CSP, лимит попыток входа. Мобильная версия, темная тема.

## Устройство
Один процесс: FastAPI + Jinja2 + htmx (веб и SSE), aiogram 3 (бот), Telethon (аккаунт), SQLite.

```
app/main.py        запуск: веб, бот, аккаунт, рассылка уведомлений
app/store.py       данные: лиды, сообщения, теги, настройки
app/bot.py         анкета, хранилище состояния в SQLite, уведомления
app/tg_account.py  подключенный аккаунт: QR-вход, фильтры, склейка
app/web.py         страницы, роли, CSRF, SSE
tests/             26 тестов (pytest), Telegram в них не поднимается
ops/               живые e2e против прод-адреса (бот, браузер, QR, уведомления), скриншоты
```

## Запуск
```
python3 -m venv venv && venv/bin/pip install fastapi "uvicorn[standard]" jinja2 aiogram telethon itsdangerous python-multipart segno
cp .env.example .env   # BOT_TOKEN, TG_API_ID/HASH, SECRET_KEY, ADMIN_PASSWORD, DEMO_PASSWORD
venv/bin/uvicorn app.main:app --port 8013
venv/bin/python -m pytest -q
```
Прод: systemd-юнит, nginx с сертификатом Let's Encrypt, данные в `data/crm.db`.
