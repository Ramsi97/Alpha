import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import INSECURE_DEFAULT_JWT_SECRET, settings
from app.core.db import engine
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


def _check_secrets() -> None:
    """Plan section 18: "Secrets in environment or a secret manager;
    rotate if exposed." The single most damaging misconfiguration this app
    could ship with is the placeholder JWT secret still active — anyone
    who has read this (public) source can then forge a valid access token
    for any user id, including an admin's. Refuse to start with it in
    `production`; just warn loudly everywhere else so local dev isn't
    blocked."""
    if settings.jwt_secret != INSECURE_DEFAULT_JWT_SECRET:
        return
    if settings.environment == "production":
        raise RuntimeError(
            "Refusing to start: JWT_SECRET is still the insecure default. Set a real secret via the JWT_SECRET env var."
        )
    logger.warning("JWT_SECRET is still the insecure default — fine for local dev, never deploy this to production.")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    _check_secrets()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="AlphaGo API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.app_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        """Plan section 18: "HTTPS only, HSTS." HSTS is normally the
        TLS-terminating proxy's job (Caddy/Nginx in front, per the
        deployment plan) but costs nothing to also send here, and browsers
        simply ignore it over plain HTTP in local dev. Deliberately does
        NOT set X-Frame-Options or a frame-ancestors CSP: this is a
        Telegram Mini App, which Telegram embeds in an iframe by design —
        a framing restriction here would break the one legitimate way
        this API's frontend is ever actually loaded."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    register_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    media_dir = Path(settings.media_dir)
    media_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=media_dir), name="media")

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz():
        checks = {"db": False, "redis": False}
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["db"] = True
        except Exception:
            pass
        try:
            await get_redis().ping()
            checks["redis"] = True
        except Exception:
            pass
        ready = all(checks.values())
        return {"status": "ok" if ready else "not_ready", "checks": checks}

    return app


app = create_app()
