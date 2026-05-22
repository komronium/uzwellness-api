from collections.abc import Callable

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings


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
            detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file"
        )
    mime = detect_mime(content)
    if mime is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type (allowed: {allowed_label})",
        )
    return content, mime
