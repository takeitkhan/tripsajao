import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import media_files, public
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.db import engine
from app.core.redis import close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name, version="1.0.0", lifespan=lifespan,
    description=("Headless multi-tenant property management API.\n\n**Auth** - server-to-server: `X-API-KEY` + `X-API-SECRET`; "
                 "dashboards: `Authorization: Bearer <JWT>`. Money values are serialised as decimal strings."),
    openapi_tags=[{"name": n} for n in ("auth", "properties", "dashboard", "pricing", "bookings", "partners",
                                        "payouts", "cms", "media", "reports", "channel", "affiliate", "docs")],
)

_OPEN = ("/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/logout", "/api/v1/auth/support-exchange",
         "/api/v1/platform/auth/login", "/api/v1/platform/auth/refresh", "/api/v1/platform/auth/logout", "/api/v1/public/")


@app.middleware("http")
async def tenant_guard(request, call_next):
    """Fail fast (before touching the DB) when an /api/v1 request carries no credentials at all.
    Real verification + RLS binding happen in `core.deps.get_ctx`."""
    path = request.url.path
    if (path.startswith("/api/v1/") and not path.startswith(_OPEN) and request.method != "OPTIONS"
            and not (request.headers.get("x-api-key") or request.headers.get("authorization"))):
        return JSONResponse({"detail": "Missing credentials"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.headers.get("x-request-id") or uuid.uuid4().hex
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    if path.startswith(("/admin", "/platform", "/register")):
        response.headers["Cache-Control"] = "no-cache"      # always re-check for a newer version of the screens
    return response


app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

app.include_router(api_router)
app.include_router(public.router)
app.include_router(media_files.router)


ADMIN_DIR = Path(__file__).parent / "static" / "admin"
app.mount("/admin", StaticFiles(directory=ADMIN_DIR, html=True), name="admin")
app.mount("/platform", StaticFiles(directory=ADMIN_DIR.parent / "platform", html=True), name="platform")
app.mount("/register", StaticFiles(directory=ADMIN_DIR.parent / "register", html=True), name="register")
app.mount("/site", StaticFiles(directory=ADMIN_DIR.parent / "site"), name="site")


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(ADMIN_DIR.parent / "site" / "index.html")


_KIND_PAGES = {"resorts": ("resort", "Resort management"), "hotels": ("hotel", "Hotel management"),
               "houseboats": ("houseboat", "Houseboat management"), "events": ("events", "Events and tours")}


def _kind_route(key: str, title: str):
    async def page():
        html = (ADMIN_DIR.parent / "site" / "kind.html").read_text(encoding="utf-8")
        return HTMLResponse(html.replace("__KIND__", key).replace("<title>Trip Sajao</title>", f"<title>{title} | Trip Sajao</title>"))
    return page


for _path, (_key, _title) in _KIND_PAGES.items():       # /resorts, /hotels, /houseboats, /events share one template
    app.add_api_route("/" + _path, _kind_route(_key, _title), methods=["GET"], include_in_schema=False)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"status": "ok"}
