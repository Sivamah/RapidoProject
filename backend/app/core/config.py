from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Orchestration Platform"

    # Declared deployment mode. Defaults to "development" so a fresh local
    # checkout still boots with the insecure dev fallbacks below (with a
    # warning). Any other value (e.g. "production") disables those
    # fallbacks and makes the app refuse to start rather than run insecure.
    ENVIRONMENT: str = "development"

    DATABASE_URL: Optional[str] = None

    POSTGRES_USER:     Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_SERVER:   Optional[str] = "localhost"
    POSTGRES_PORT:     Optional[str] = "5432"
    POSTGRES_DB:       Optional[str] = None

    # No hard default: when ENVIRONMENT != "development" and SECRET_KEY is
    # unset (or still equals the known dev fallback), the app raises at
    # import time below instead of starting insecurely. In development mode
    # only, a dev fallback is applied and a startup warning is logged.
    SECRET_KEY: Optional[str] = None

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    ALLOWED_ORIGINS: str = "http://localhost:5173"

    # Google Maps API key (optional) — enables real distance/time/route data
    # in the DMFE engine.  When absent, haversine-based fallbacks are used.
    GOOGLE_MAPS_API_KEY: Optional[str] = None


    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.DATABASE_URL:
            if self.DATABASE_URL.startswith("postgres://"):
                return self.DATABASE_URL.replace("postgres://", "postgresql://", 1)
            return self.DATABASE_URL
        if self.POSTGRES_USER and self.POSTGRES_PASSWORD and self.POSTGRES_DB:
            return (
                f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        return f"sqlite:///{BACKEND_DIR / 'dmfe_dev.db'}"

    # Absolute path, independent of the CWD the backend is started from.
    # A relative ".env" breaks SECRET_KEY/DATABASE_URL/ALLOWED_ORIGINS
    # whenever uvicorn is launched from the repo root, which prevents
    # the backend from booting and makes login look broken.
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        extra="ignore",
    )


settings = Settings()

_DEV_SECRET_FALLBACK = "aiorch-dev-secret-change-me-in-production"
_is_dev = settings.ENVIRONMENT == "development"

if settings.SECRET_KEY in ("", None):
    if _is_dev:
        import logging
        logging.getLogger("aiorch").warning(
            "SECRET_KEY not configured — using insecure development fallback. "
            "Set SECRET_KEY in backend/.env before deploying with ENVIRONMENT != 'development'."
        )
        settings.SECRET_KEY = _DEV_SECRET_FALLBACK
    else:
        raise RuntimeError(
            "SECRET_KEY is not set and ENVIRONMENT is not 'development'. Refusing to start "
            "with an insecure default outside development. Set SECRET_KEY in backend/.env "
            "(or set ENVIRONMENT=development for local use)."
        )
elif settings.SECRET_KEY == _DEV_SECRET_FALLBACK and not _is_dev:
    raise RuntimeError(
        "SECRET_KEY is set to the known development fallback value outside development. "
        "Set a real SECRET_KEY in backend/.env."
    )
