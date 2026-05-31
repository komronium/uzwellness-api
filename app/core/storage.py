from pathlib import Path
from typing import Protocol

import aiofiles
from fastapi import HTTPException, status

from app.core.config import settings


class StorageBackend(Protocol):
    async def save(self, *, key: str, content: bytes, content_type: str) -> str: ...

    async def delete(self, *, key: str) -> None: ...


def url_to_key(url: str) -> str:
    """Convert a saved file URL back to its storage key.

    Storage backends save with `key` and return a URL like
    `{prefix}/{key}`. We need the key back to delete. If the URL doesn't
    start with our prefix (e.g. an externally-hosted file), return it as-is.
    """
    prefix = settings.UPLOAD_URL_PREFIX.rstrip("/") + "/"
    return url[len(prefix) :] if url.startswith(prefix) else url


def _validate_key(key: str) -> None:
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid storage key"
        )
    if ".." in Path(key).parts or key.startswith("/") or "\x00" in key or "\\" in key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid storage key"
        )


class LocalStorage:
    def __init__(self, base_dir: Path, url_prefix: str) -> None:
        self.base_dir = base_dir.resolve()
        self.url_prefix = url_prefix.rstrip("/")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        _validate_key(key)
        target = (self.base_dir / key).resolve()
        try:
            target.relative_to(self.base_dir)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid storage key",
            ) from exc
        return target

    async def save(self, *, key: str, content: bytes, content_type: str) -> str:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(target, "wb") as f:
            await f.write(content)
        return f"{self.url_prefix}/{key}"

    async def delete(self, *, key: str) -> None:
        target = self._resolve(key)
        target.unlink(missing_ok=True)


def get_storage() -> StorageBackend:
    return LocalStorage(
        base_dir=Path(settings.UPLOAD_DIR),
        url_prefix=settings.UPLOAD_URL_PREFIX,
    )


_IMAGE_MAGIC: dict[str, tuple[bytes, ...]] = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}


def detect_image_mime(data: bytes) -> str | None:
    for mime, prefixes in _IMAGE_MAGIC.items():
        for prefix in prefixes:
            if data.startswith(prefix):
                return mime
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def detect_document_mime(data: bytes) -> str | None:
    image = detect_image_mime(data)
    if image is not None:
        return image
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


MIME_EXTENSIONS: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}
