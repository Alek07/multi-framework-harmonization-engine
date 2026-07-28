from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "server"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "local"

    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"

    # The POC ships no Alembic revision: the schema (audit log included, UCM-11)
    # is created from the models at startup so `docker compose up` works on a
    # foreign machine with no migration step. The tests own their own schema.
    CREATE_TABLES_ON_STARTUP: bool = True

    # Versioned catalog (UCM-4/UCM-7): read-only JSON, frozen in Git.
    CATALOG_PATH: str = "data/catalog/catalog.v0.1.0.json"

    # Versioned engine rules (UCM-8): precedence per zone + declared contradictions.
    RULES_PATH: str = "data/rules/precedence.v0.1.0.json"

    # Versioned gating rules (UCM-9): which mechanisms an asset profile rules out.
    GATING_PATH: str = "data/rules/gating.v0.1.0.json"

    # Versioned prioritisation rules (UCM-10): SL mandates, dependencies, ordinal cost.
    PRIORITIZATION_PATH: str = "data/rules/prioritization.v0.1.0.json"

    # Hand-written asset profiles (UCM-1/UCM-2), inputs frozen in Git.
    PROFILES_DIR: str = "data/profiles"

    # --- AI layer (M2) --------------------------------------------------------
    # None of this is a tuning knob. Every value below governs what the LLM and
    # the retriever produce, so each one is recorded in the audit trail next to
    # the catalog/rules versions (UCM-11) and a run can be replayed on a foreign
    # machine (UCM-22). Changing one changes the result: it is a versioned act.

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "qwen2.5:7b-instruct-q4_K_M"
    # Manifest digest of the pulled model, checked against Ollama's `/api/tags`
    # at startup. Ollama tags are mutable, so the tag alone pins nothing.
    # Real 8 GB fallback — qwen2.5:3b-instruct-q4_K_M:
    #   357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b
    LLM_MODEL_DIGEST: str = "845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e"

    # Greedy decoding with a fixed seed. top_k/top_p/repeat_penalty are pinned
    # rather than left to Ollama's defaults, which move between releases — an
    # unpinned default is a reproducibility hole that nothing would report.
    LLM_TEMPERATURE: float = 0.0
    LLM_SEED: int = 42
    LLM_TOP_K: int = 1
    LLM_TOP_P: float = 1.0
    LLM_REPEAT_PENALTY: float = 1.0
    LLM_NUM_CTX: int = 8192
    LLM_NUM_PREDICT: int = 2048
    # Retries on Pydantic validation failure (UCM-12). A retry is not a reroll:
    # Pydantic AI appends the validation error to the message history, so the
    # prompt genuinely differs and the fixed seed still holds.
    LLM_MAX_RETRIES: int = 3
    LLM_TIMEOUT_SECONDS: int = 180

    QDRANT_URL: str = "http://localhost:6333"
    # The collection is suffixed with the catalog version when it is populated,
    # so a catalog bump can never retrieve against stale vectors (UCM-13).
    QDRANT_COLLECTION_PREFIX: str = "catalog"
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-base"
    EMBEDDING_DIM: int = 768
    EMBEDDING_CACHE_DIR: str = "./.cache/models"
    # Retrieval widens candidate coverage and never narrows it. RAG_TOP_K caps
    # how many *extra* candidates are offered per capability; a capability left
    # with none is declared an explicit gap, never dropped. There is deliberately
    # no score threshold: a threshold discards candidates silently, which is the
    # one thing the engine may not do.
    RAG_TOP_K: int = 10

    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
