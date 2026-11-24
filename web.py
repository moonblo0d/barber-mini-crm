"""Веб-частина: лендинг, публічний API для форми та захищена адмін-панель."""
import asyncio
import base64
import logging
import re
import time
from collections import defaultdict, deque
from typing import Optional

from aiohttp import web

import db
from config import LANDING_DIR, PANEL_DIR, PANEL_PASSWORD, SERVICES, STATUSES

log = logging.getLogger(__name__)
PHONE_RE = re.compile(r"^\+?[\d\s\-()]{9,18}$")

# Простий антиспам: не більше 5 заявок з однієї IP за 10 хвилин.
_RATE_WINDOW = 600
_RATE_LIMIT = 5
_recent: dict[str, deque] = defaultdict(deque)


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    q = _recent[ip]
    while q and now - q[0] > _RATE_WINDOW:
        q.popleft()
    if len(q) >= _RATE_LIMIT:
        return True
    q.append(now)
    return False


def _authorized(request: web.Request) -> bool:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Basic "):
        return False
    try:
        user, _, password = base64.b64decode(header[6:]).decode().partition(":")
    except Exception:
        return False
    return user == "admin" and password == PANEL_PASSWORD


@web.middleware
async def auth_middleware(request: web.Request, handler):
    protected = request.path.startswith("/admin") or (
        request.path.startswith("/api/leads") and not (request.path == "/api/leads" and request.method == "POST")
    )
    if protected and not _authorized(request):
        return web.Response(
            status=401,
            text="Потрібна авторизація",
            headers={"WWW-Authenticate": 'Basic realm="Mini CRM"'},
        )
    return await handler(request)


# ---------- Сторінки ----------

async def landing(_: web.Request) -> web.FileResponse:
    return web.FileResponse(LANDING_DIR / "index.html")


async def panel(_: web.Request) -> web.FileResponse:
    return web.FileResponse(PANEL_DIR / "index.html")


# ---------- API ----------

def _clean(value: Optional[str], max_len: int) -> str:
    return (value or "").strip()[:max_len]


async def api_create_lead(request: web.Request) -> web.Response:
    ip = request.headers.get("X-Forwarded-For", request.remote or "?").split(",")[0].strip()
    if _rate_limited(ip):
        return web.json_response({"ok": False, "error": "Забагато заявок. Спробуйте пізніше."}, status=429)
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Некоректний запит"}, status=400)

    if data.get("website"):  # приховане поле-пастка для ботів
        return web.json_response({"ok": True})

    name = _clean(data.get("name"), 60)
    phone = _clean(data.get("phone"), 20)
    service = _clean(data.get("service"), 60)
    errors = {}
    if len(name) < 2:
        errors["name"] = "Вкажіть ім'я"
    if not PHONE_RE.match(phone):
        errors["phone"] = "Вкажіть коректний номер"
    if service not in SERVICES:
        errors["service"] = "Оберіть послугу"
    if errors:
        return web.json_response({"ok": False, "errors": errors}, status=422)

    lead = db.create_lead(
        name=name,
        phone=phone,
        service=service,
        preferred_time=_clean(data.get("preferred_time"), 100),
        comment=_clean(data.get("comment"), 500),
        source="website",
    )
    bot = request.app.get("bot")
    if bot is not None:
        from bot import notify_admin  # локальний імпорт, щоб веб працював і без бота

        # Сповіщення у фоні: клієнт не чекає, поки відповість Telegram
        task = asyncio.create_task(notify_admin(bot, lead))
        request.app["bg_tasks"].add(task)
        task.add_done_callback(request.app["bg_tasks"].discard)
    return web.json_response({"ok": True, "id": lead["id"]}, status=201)


async def api_list_leads(request: web.Request) -> web.Response:
    status = request.query.get("status") or None
    if status and status not in STATUSES:
        return web.json_response({"error": "Невідомий статус"}, status=400)
    return web.json_response({"leads": db.list_leads(status), "stats": db.stats(), "statuses": STATUSES})


async def api_set_status(request: web.Request) -> web.Response:
    lead_id = int(request.match_info["lead_id"])
    data = await request.json()
    status = data.get("status")
    if status not in STATUSES:
        return web.json_response({"error": "Невідомий статус"}, status=400)
    lead = db.set_status(lead_id, status)
    if lead is None:
        return web.json_response({"error": "Не знайдено"}, status=404)
    return web.json_response({"lead": lead})


async def api_services(_: web.Request) -> web.Response:
    return web.json_response({"services": SERVICES})


def create_app(bot=None) -> web.Application:
    app = web.Application(middlewares=[auth_middleware])
    app["bg_tasks"] = set()
    if bot is not None:
        app["bot"] = bot
    app.router.add_get("/", landing)
    app.router.add_get("/admin", panel)
    app.router.add_get("/api/services", api_services)
    app.router.add_post("/api/leads", api_create_lead)
    app.router.add_get("/api/leads", api_list_leads)
    app.router.add_post("/api/leads/{lead_id:\\d+}/status", api_set_status)
    app.router.add_static("/assets/", LANDING_DIR / "assets", show_index=False)
    return app
