from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import register_exception_handlers
from app.core.middleware import register_middleware
from app.users.router import router as users_router


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

    health_router = APIRouter()

    @health_router.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    api_router = APIRouter()
    api_router.include_router(health_router, tags=["health"])
    api_router.include_router(users_router, prefix="/users", tags=["users"])

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()
