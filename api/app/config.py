from functools import lru_cache
from urllib.parse import urlsplit
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./pharmaone.db"
    supabase_url: str = ""
    supabase_jwt_audience: str = "authenticated"
    tinyfish_api_key: str = ""
    sarvam_api_key: str = ""
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    pharmaone_env: str = "local"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

    @staticmethod
    def _exact_https_origin(value: str) -> bool:
        parsed = urlsplit(value)
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.path and not parsed.query and not parsed.fragment and "*" not in value


@lru_cache
def settings() -> Settings:
    return Settings()
