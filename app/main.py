import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.api.openapi_responses import COMMON_ERROR_RESPONSES
from app.api.openapi_tags import OPENAPI_TAGS
from app.core.config import settings
from app.core.redis_client import close_redis, get_redis
from app.services.exchange_rate_sync import run_exchange_rate_sync_loop

logger = logging.getLogger("uzwellness.validation")


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


@app.exception_handler(RequestValidationError)
async def log_request_validation_error(
    request: Request, exc: RequestValidationError
) -> Response:
    """Log which fields a rejected request got wrong, then answer as usual.

    A 422 reaches the browser as an opaque array the UI usually swallows, so
    without this the server keeps no trace of *why* a form failed. Only the
    field path, error type and message are logged — never the submitted value,
    which would put passwords and guest data in the log.
    """

    logger.warning(
        "422 %s %s: %s",
        request.method,
        request.url.path,
        "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: "
            f"{error['type']} — {error['msg']}"
            for error in exc.errors()
        ),
    )
    return await request_validation_exception_handler(request, exc)


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
