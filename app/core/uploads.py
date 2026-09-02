from collections.abc import Callable

from fastapi import HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.image_processing import to_webp
from app.core.storage import detect_image_mime


async def read_upload(
    file: UploadFile,
    *,
    detect_mime: Callable[[bytes], str | None],
    allowed_label: str,
) -> tuple[bytes, str]:
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                "This file is larger than the "
                f"{settings.MAX_UPLOAD_SIZE_MB} MB limit. "
                "Please upload a smaller one."
            ),
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty",
        )
    mime = detect_mime(content)
    if mime is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"This file type is not supported. Allowed formats: {allowed_label}."
            ),
        )
    return content, mime


async def read_image_upload_as_webp(file: UploadFile) -> tuple[bytes, str]:
    content, _mime = await read_upload(
        file, detect_mime=detect_image_mime, allowed_label="JPEG, PNG, WebP"
    )
    # Decoding, resampling and re-encoding a photo is seconds of pure CPU on a
    # large upload. On the event loop that is seconds in which the server
    # answers nobody at all, so it runs on a worker thread — Pillow releases
    # the GIL for most of it.
    return await run_in_threadpool(to_webp, content)
