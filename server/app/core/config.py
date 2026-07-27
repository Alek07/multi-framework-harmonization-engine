from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "server"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "local"

    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"

    # Versioned catalog (UCM-4/UCM-7): read-only JSON, frozen in Git.
    CATALOG_PATH: str = "data/catalog/catalog.v0.1.0.json"

    # Versioned engine rules (UCM-8): precedence per zone + declared contradictions.
    RULES_PATH: str = "data/rules/precedence.v0.1.0.json"

    # Versioned gating rules (UCM-9): which mechanisms an asset profile rules out.
    GATING_PATH: str = "data/rules/gating.v0.1.0.json"

    # Hand-written asset profiles (UCM-1/UCM-2), inputs frozen in Git.
    PROFILES_DIR: str = "data/profiles"

    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
