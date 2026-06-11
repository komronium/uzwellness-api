import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.api.openapi_tags import OPENAPI_TAGS
from app.api.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.config import settings
from app.core.redis_client import close_redis, get_redis
from app.services.exchange_rate_sync import run_exchange_rate_sync_loop


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await get_redis()
    rate_sync_task: asyncio.Task | None = None
    if settings.EXCHANGE_RATE_SYNC_ENABLED:
        rate_sync_task = asyncio.create_task(run_exchange_rate_sync_loop())
    yield
    if rate_sync_task is not None:
        rate_sync_task.cancel()
        with suppress(asyncio.CancelledError):
            await rate_sync_task
    await close_redis()


app = FastAPI(
    title=settings.PROJECT_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
    responses=COMMON_ERROR_RESPONSES,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_PREFIX)

uploads_dir = Path(settings.UPLOAD_DIR)
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    settings.UPLOAD_URL_PREFIX,
    StaticFiles(directory=uploads_dir),
    name="uploads",
)


@app.get("/", tags=["System"])
async def root() -> dict[str, str]:
    return {"name": settings.PROJECT_NAME, "docs": "/docs"}
