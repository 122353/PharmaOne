from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./pharmaone.db"
    supabase_url: str = ""
    supabase_jwt_audience: str = "authenticated"
    tinyfish_encryption_key: str = ""
    tinyfish_service_key: str = ""
    allowed_origins: str = "http://localhost:3000"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def settings() -> Settings:
    return Settings()
