from pydantic_settings import BaseSettings, SettingsConfigDict


INSECURE_DEFAULT_JWT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "development" (default) | "staging" | "production". Only gates the
    # insecure-default-secret startup check below (app/main.py) — nothing
    # else in the app branches on this today.
    environment: str = "development"

    # Telegram
    bot_token: str = "dev-placeholder-bot-token"
    bot_username: str = "alphago_dev_bot"
    mini_app_short_name: str = "play"
    webhook_url: str = ""
    webhook_secret: str = ""

    # Infra
    database_url: str = "postgresql+asyncpg://ramsi@/alphago_dev"
    # SQLAlchemy's own defaults (pool_size=5, max_overflow=10 — 15 total)
    # turned out to be the real bottleneck under load (see server/README.md's
    # load-test section): with one connection held per in-flight request,
    # 15 total connections meant request #16 onward just queued for a free
    # one, not an error — so it showed up as rising latency, not failures,
    # until it was traced back here. Comfortably under Postgres' own
    # default max_connections=100 even with a couple of API processes.
    db_pool_size: int = 20
    db_max_overflow: int = 20
    redis_url: str = "fakeredis://"  # plan section 2 calls for real Redis 7 in production;
    # this environment has no Redis server and no way to install one (no sudo, no docker
    # network access) — "fakeredis://" is a sentinel this codebase recognizes to use an
    # in-memory redis-protocol-compatible client instead. Set a real redis:// URL in any
    # environment that actually has Redis. See app/core/redis.py.

    # Auth
    jwt_secret: str = INSECURE_DEFAULT_JWT_SECRET
    jwt_ttl_seconds: int = 3600
    initdata_max_age_seconds: int = 86400

    # CORS / iframe origins
    app_origin: str = "http://localhost:5173"
    games_origin: str = "http://localhost:8731"

    # Admin bootstrap
    admin_telegram_ids: str = ""  # comma-separated

    # Observability
    sentry_dsn: str = ""

    # Share / score cards (plan section 15)
    public_base_url: str = "http://localhost:8000"
    media_dir: str = "media"

    # Notifications
    notify_rate_per_second: int = 25

    @property
    def admin_telegram_id_list(self) -> list[int]:
        return [int(x) for x in self.admin_telegram_ids.split(",") if x.strip()]


settings = Settings()
