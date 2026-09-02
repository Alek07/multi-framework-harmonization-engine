from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    PROJECT_NAME: str = "server"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "local"
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"
    CREATE_TABLES_ON_STARTUP: bool = True
    CATALOG_PATH: str = "data/catalog/catalog.v0.5.0.json"
    RULES_PATH: str = "data/rules/precedence.v0.1.0.json"
    GATING_PATH: str = "data/rules/gating.v0.2.0.json"
    PRIORITIZATION_PATH: str = "data/rules/prioritization.v0.2.0.json"
    PROFILES_DIR: str = "data/profiles"

    # --- AI layer (M2) --------------------------------------------------------
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "qwen2.5:7b-instruct-q4_K_M"
    LLM_MODEL_DIGEST: str = "845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e"
    LLM_TEMPERATURE: float = 0.0
    LLM_SEED: int = 42
    LLM_TOP_P: float = 1.0
    LLM_NUM_CTX: int = 8192
    LLM_NUM_PREDICT: int = 2048
    LLM_MAX_RETRIES: int = 3
    LLM_TIMEOUT_SECONDS: int = 180
    LLM_KEEP_ALIVE: str = "30m"
    LLM_WARM_ON_STARTUP: bool = True
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION_PREFIX: str = "catalog"
    QDRANT_TIMEOUT_SECONDS: int = 30
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-base"
    EMBEDDING_DIM: int = 768
    EMBEDDING_CACHE_DIR: str = "./.cache/models"
    EMBEDDING_NUM_THREADS: int = 1
    RAG_RETRIEVAL_DEPTH: int = 50
    RAG_TOP_K: int = 10
    RAG_CUT_TIE_EPSILON: float = 0.01
    RAG_MAX_K: int = 16
    RAG_FRAMEWORK_CAP: int = 4

    RAG_POPULATE_ON_STARTUP: bool = True
    EXPLAIN_ENABLED: bool = True
    EXPLAIN_TIMEOUT_SECONDS: int = 600

    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
