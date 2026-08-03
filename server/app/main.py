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
# than it usually would: populating the index at startup is best-effort by design
# (UCM-13), and a failure that is only *logged* has to actually be visible to
# whoever ran `docker compose up`. No-op when the root logger is already set up.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")
# httpx logs one line per request, and loading the embedding model makes ~25 of
# them to the model hub. They would bury the two lines that actually say whether
# the index came up.
logging.getLogger("httpx").setLevel(logging.WARNING)


async def _populate_catalog_index() -> None:
    """Populate Qdrant from the catalog (UCM-13), off the event loop and off the path.

    Deliberately a background task rather than a step of startup. Building the
    index means loading a ~1.1 GB embedding model — downloaded on first run — and
    talking to a container that may still be coming up, and the API has to serve
    `/health` in the meantime (the same reasoning as the lazy Ollama check in
    UCM-12). The index is derived data: a failure here costs a rebuild, never
    state, so it is logged and never fatal. Retrieval calls `ensure` itself before
    its first query, so a backend that started before Qdrant did still works.
    """
    from app.retrieval.index import CatalogIndex

    try:
        index = CatalogIndex()
        rebuilt = await asyncio.to_thread(index.ensure)
        logger.info(
            "Qdrant: índice %s %s", index.collection, "poblado" if rebuilt else "ya disponible"
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Qdrant: no se pudo poblar el índice del catálogo al arranque (%s). La API sigue "
            "en pie; la recuperación lo reintentará en su primera consulta.",
            exc,
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Bring up the SQLite schema the audit log lives in (UCM-11)."""
    if settings.CREATE_TABLES_ON_STARTUP:
        await init_db()

    index_task = (
        asyncio.create_task(_populate_catalog_index())
        if settings.RAG_POPULATE_ON_STARTUP
        else None
    )
    try:
        yield
    finally:
        if index_task is not None and not index_task.done():
            index_task.cancel()
            with suppress(asyncio.CancelledError):
                await index_task


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        lifespan=lifespan,
    )

    register_middleware(app)
    register_exception_handlers(app)

    # Liveness probe, not part of the API surface. The closed surface is the
    # five endpoints of §7.4 (M3); this one exists so the compose healthcheck
    # can tell a started container from a serving one (UCM-20).
    health_router = APIRouter()

    @health_router.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    root_router = APIRouter()
    root_router.include_router(health_router, tags=["health"])
    # The five endpoints of §7.4, declared as data in `app/api/router.py` so that
    # a sixth one cannot appear without the surface test noticing (invariant 4).
    root_router.include_router(api_router())

    app.include_router(root_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()
