"""Settings read from the environment (docs/architecture.md, "Environment variables")."""

from functools import lru_cache

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    # Required, no default: the app refuses to start without it (spec section 8).
    JWT_SECRET: str = Field(min_length=1)
    # Token lifetime in minutes: 8 hours (rule 5.14).
    JWT_EXPIRE_MINUTES: int = 480
    DATABASE_URL: str = "sqlite:///./lab_booking.db"
    # Comma-separated list of allowed frontend origins.
    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        problems = ", ".join(str(e["loc"][0]) for e in exc.errors() if e["loc"])
        raise RuntimeError(
            f"Invalid configuration ({problems}). JWT_SECRET must be set in the "
            "environment; see docs/architecture.md, 'Environment variables'."
        ) from exc
