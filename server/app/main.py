import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import APIRouter, FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import register_exception_handlers
from app.core.middleware import register_middleware

logger = logging.getLogger(__name__)

# Uvicorn configures its own loggers and leaves the root one without a handler, so
# without this the application's own messages go nowhere. That matters here more
# than usual: populating the index at startup is best-effort by design, and a
# failure that is only *logged* has to be visible to whoever ran
# `docker compose up`. No-op when the root logger is already set up.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")
# httpx logs one line per request, and loading the embedding model makes ~25 of
# them to the model hub. They would bury the two lines that actually say whether
# the index came up.
logging.getLogger("httpx").setLevel(logging.WARNING)


async def _populate_catalog_index() -> None:
    """Populate Qdrant from the catalog, off the event loop and off the request path.

    Deliberately a background task rather than a step of startup: building the
    index loads a ~1.1 GB embedding model (downloaded on first run) and talks to a
    container that may still be coming up, while the API must keep serving
    `/health`. The index is derived data — a failure costs a rebuild, never state,
    so it is logged and never fatal; retrieval calls `ensure` before its first
    query, so a backend that started before Qdrant still works.

    The warm-up is part of the same job: once the collection exists, `ensure`
    returns without touching the model, so the weights are deserialised here
    rather than inside the operator's first `POST /candidates`.
    """
    from app.retrieval.index import CatalogIndex

    try:
        index = CatalogIndex()
        rebuilt = await asyncio.to_thread(index.ensure)
        logger.info(
            "Qdrant: índice %s %s", index.collection, "poblado" if rebuilt else "ya disponible"
        )
        await asyncio.to_thread(index.warm)
        logger.info("Embeddings: modelo listo; la primera consulta ya no lo carga")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Recuperación: no se pudo dejar lista al arranque — índice o modelo (%s). La API "
            "sigue en pie; la primera consulta lo reintentará, y le costará la espera.",
            exc,
        )


async def _warm_language_model() -> None:
    """Load the 7B into Ollama's memory, off the event loop and off the request path.

    Same contract as the index warm-up above, against a measured cost: 262 s for a
    cold parse against 77 s for a warm one, same answer. The compose entrypoint
    preloads too; this covers a backend restarted after Ollama evicted the model,
    and the setup where the backend runs natively.
    """
    from app.parse.ollama import warm_model

    try:
        await warm_model()
        logger.info("Ollama: modelo %s cargado en memoria; la primera lectura ya no lo carga",
                    settings.LLM_MODEL)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Ollama: no se pudo precargar %s al arranque (%s). La API sigue en pie; la primera "
            "lectura de una descripción lo cargará, y le costará la espera.",
            settings.LLM_MODEL,
            exc,
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Bring up the SQLite schema the audit log lives in.

    The two warm-ups then run concurrently in the background. They compete for CPU
    on a small machine, which still beats paying both inside the operator's first
    two clicks.
    """
    if settings.CREATE_TABLES_ON_STARTUP:
        await init_db()

    tasks = [
        task
        for task in (
            asyncio.create_task(_populate_catalog_index())
            if settings.RAG_POPULATE_ON_STARTUP
            else None,
            asyncio.create_task(_warm_language_model()) if settings.LLM_WARM_ON_STARTUP else None,
        )
        if task is not None
    ]
    try:
        yield
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        lifespan=lifespan,
    )

    register_middleware(app)
    register_exception_handlers(app)

    # Liveness probe, not part of the closed API surface; it lets the compose
    # healthcheck tell a started container from a serving one.
    health_router = APIRouter()

    @health_router.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    root_router = APIRouter()
    root_router.include_router(health_router, tags=["health"])
    # The closed API surface, declared as data in `app/api/router.py` so no
    # endpoint can appear without the surface test noticing.
    root_router.include_router(api_router())

    app.include_router(root_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()
