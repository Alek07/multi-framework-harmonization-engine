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

    # Versioned catalog (UCM-4/UCM-7/UCM-43): read-only JSON, frozen in Git. From
    # v0.2.0 this file is a manifest: it carries the capabilities and names one
    # source per framework, which the loader merges before validating (the split
    # is authoring ergonomics and changes nothing the engine sees).
    CATALOG_PATH: str = "data/catalog/catalog.v0.2.0.json"

    # Versioned engine rules (UCM-8): precedence per zone + declared contradictions.
    RULES_PATH: str = "data/rules/precedence.v0.1.0.json"

    # Versioned gating rules (UCM-9): which mechanisms an asset profile rules out.
    GATING_PATH: str = "data/rules/gating.v0.1.0.json"

    # Versioned prioritisation rules (UCM-10): SL mandates, dependencies, ordinal cost.
    PRIORITIZATION_PATH: str = "data/rules/prioritization.v0.2.0.json"

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

    # Greedy decoding with a fixed seed. Only the four settings below reach the
    # model through Ollama's OpenAI-compatible endpoint (UCM-12): it maps a fixed
    # set of OpenAI fields and silently drops anything else, `top_k` and
    # `repeat_penalty` included. Those two are left at the Ollama server's
    # defaults and pinned by the *image* digest in the compose file — declared in
    # `app/parse/agent.py` rather than faked with a setting that does nothing.
    LLM_TEMPERATURE: float = 0.0
    LLM_SEED: int = 42
    LLM_TOP_P: float = 1.0
    # Context window. Not a request field either: it is applied server-side via
    # OLLAMA_CONTEXT_LENGTH in the compose file, which reads this same value.
    # Ollama's own default (4096) truncates this prompt plus its JSON schema.
    LLM_NUM_CTX: int = 8192
    LLM_NUM_PREDICT: int = 2048
    # Retries on Pydantic validation failure (UCM-12). A retry is not a reroll:
    # Pydantic AI appends the validation error to the message history, so the
    # prompt genuinely differs and the fixed seed still holds.
    LLM_MAX_RETRIES: int = 3
    LLM_TIMEOUT_SECONDS: int = 180
    # Residency window, sent with the preload. Not a decoding parameter, so it stays
    # out of the provenance. Mirrors OLLAMA_KEEP_ALIVE in the compose file; a native
    # Ollama evicts after 5 min and the next parse pays ~185 s to reload.
    LLM_KEEP_ALIVE: str = "30m"
    # Preload at startup, like RAG_POPULATE_ON_STARTUP. Off, the parse still works —
    # it just pays the load on the first request.
    LLM_WARM_ON_STARTUP: bool = True

    QDRANT_URL: str = "http://localhost:6333"
    # The collection is suffixed with the catalog version *and* a digest of the
    # catalog it was built from, so a catalog bump — or an edit made in place,
    # which the conventions forbid — can never retrieve against stale vectors
    # (UCM-13). The full name is computed in `app/retrieval/index.py`.
    QDRANT_COLLECTION_PREFIX: str = "catalog"
    QDRANT_TIMEOUT_SECONDS: int = 30
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-base"
    EMBEDDING_DIM: int = 768
    EMBEDDING_CACHE_DIR: str = "./.cache/models"
    # Pinned to one thread: a multi-threaded reduction adds its partial sums in
    # whatever order the threads finish, so the vectors would not be identical
    # from run to run even on the same machine. 69 controls encoded once at index
    # time make the cost irrelevant next to the reproducibility (see
    # `app/retrieval/embeddings.py` for what this does and does not guarantee).
    EMBEDDING_NUM_THREADS: int = 1
    # Retrieval widens candidate coverage and never narrows it. RAG_TOP_K is how
    # many *extra* candidates the query reserves per capability: it asks the index
    # for RAG_TOP_K plus the catalog's own candidates, so a capability whose
    # candidates all come back as confirmations still gets RAG_TOP_K suggestions.
    # Nothing is discarded after the query — the bound lives in the query and is
    # recorded in the provenance. There is deliberately no score threshold either:
    # a threshold discards candidates silently, which is the one thing the engine
    # may not do.
    RAG_TOP_K: int = 10
    # Populate Qdrant from the catalog at startup. Best effort and never fatal:
    # the index is derived data, it is rebuilt idempotently, and the API must come
    # up on a machine where Qdrant is still starting or the model still
    # downloading. Retrieval ensures the index itself before its first query.
    RAG_POPULATE_ON_STARTUP: bool = True

    # LLM explanations of the candidates (UCM-14). P1 and strictly presentational:
    # the prose never reaches ranking, selection or coverage, so switching it off
    # changes what the operator *reads* and nothing about the baseline. Off is a
    # declared state, reported per candidate as `disabled` with the engine's own
    # rationale in place of the model's — never an empty screen.
    EXPLAIN_ENABLED: bool = True
    # Its own timeout, and the reason is a measurement rather than a preference.
    # One request explains every candidate of a capability: with RAG_TOP_K=10 plus
    # the catalog's own, that is ~12 paragraphs, ~900 generated tokens. The 7B
    # decodes at ~3.5 tok/s on the reference CPU machine, so the batch needs ~4-5
    # minutes and LLM_TIMEOUT_SECONDS (sized for a single parse) cuts it off
    # mid-way. Timing out is not a data failure here — the candidates and their
    # deterministic justifications are already on screen — but it would make the
    # feature never work on the target machine, which is not a trade worth making
    # silently. This is also why the layer is on demand and never eager.
    EXPLAIN_TIMEOUT_SECONDS: int = 600

    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
