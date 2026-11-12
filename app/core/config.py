from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "PropSaaS Headless API"
    environment: str = "development"

    database_url: str                 # RLS-enforced app role
    database_url_system: str          # BYPASSRLS role (workers only)
    database_url_migrations: str = ""  # table-owner role (Alembic only)
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    api_secret_pepper: str            # HMAC pepper for API secrets

    cookie_encryption_key: str        # Fernet key
    referral_cookie_name: str = "_ref_token"
    referral_cookie_days: int = 30
    cookie_secure: bool = True
    cors_origins: str = ""            # comma separated, e.g. http://localhost:3000,https://app.example.com

    hold_ttl_seconds: int = 600
    default_deposit_percent: int = 50
    default_min_payout: Decimal = Decimal("1000")
    public_api_base_url: str = "http://localhost:8000"

    media_root: str = "media_store"            # where uploaded files are kept (a Docker volume in compose)
    max_image_mb: int = 15
    max_video_mb: int = 300
    media_quota_mb: int = 5000                 # default per tenant; the super admin can set a limit per tenant

    registration_mode: str = "approval"        # approval = new businesses wait for the super admin | open = active at once | closed
    support_session_minutes: int = 60


    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
