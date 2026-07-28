from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import register_exception_handlers
from app.core.middleware import register_middleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Bring up the SQLite schema the audit log lives in (UCM-11)."""
    if settings.CREATE_TABLES_ON_STARTUP:
        await init_db()
    yield


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

    api_router = APIRouter()
    api_router.include_router(health_router, tags=["health"])

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()
