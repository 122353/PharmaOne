from functools import lru_cache
from urllib.parse import parse_qs, urlsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./pharmaone.db"
    db_sslmode: str = "auto"
    supabase_url: str = ""
    supabase_jwt_audience: str = "authenticated"
    tinyfish_api_key: str = ""
    sarvam_api_key: str = ""
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    pharmaone_env: str = "local"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value):
        """Accept normal provider URLs while keeping SQLAlchemy on psycopg 3."""
        text = str(value or "")
        if text.startswith("postgres://"):
            return "postgresql+psycopg://" + text[len("postgres://"):]
        if text.startswith("postgresql://"):
            return "postgresql+psycopg://" + text[len("postgresql://"):]
        return text

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def normalize_allowed_origins(cls, value):
        # CORS origins are exact origins; a trailing slash makes the browser value differ.
        parts = [part.strip().rstrip("/") for part in str(value or "").split(",") if part.strip()]
        return ",".join(parts)

    @field_validator("db_sslmode")
    @classmethod
    def validate_sslmode(cls, value):
        mode = str(value or "auto").strip().lower()
        allowed = {"auto", "disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
        if mode not in allowed:
            raise ValueError("DB_SSLMODE must be auto, disable, allow, prefer, require, verify-ca, or verify-full")
        return mode

    @model_validator(mode="after")
    def validate_public_deployment(self):
        if self.pharmaone_env != "production":
            return self
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("Production requires a PostgreSQL DATABASE_URL")
        supabase = urlsplit(self.supabase_url)
        if supabase.scheme != "https" or not supabase.hostname:
            raise ValueError("Production requires an HTTPS SUPABASE_URL")
        origins = [value.strip() for value in self.allowed_origins.split(",")]
        if not origins or any(not self._exact_https_origin(value) for value in origins):
            raise ValueError("Production requires exact HTTPS ALLOWED_ORIGINS")
        return self

    @property
    def resolved_db_sslmode(self) -> str | None:
        """Resolve SSL automatically without breaking the local docker-compose database."""
        normalized = self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        parsed = urlsplit(normalized)
        if parse_qs(parsed.query).get("sslmode"):
            return None
        if self.db_sslmode != "auto":
            return self.db_sslmode
        if parsed.hostname in {"localhost", "127.0.0.1", "::1", "db"}:
            return "disable"
        return "require"

    @staticmethod
    def _exact_https_origin(value: str) -> bool:
        parsed = urlsplit(value)
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.path and not parsed.query and not parsed.fragment and "*" not in value


@lru_cache
def settings() -> Settings:
    return Settings()
