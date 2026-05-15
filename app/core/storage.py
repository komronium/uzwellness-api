from pathlib import Path
from typing import Protocol

from app.core.config import settings


class StorageBackend(Protocol):
    async def save(
        self, *, key: str, content: bytes, content_type: str
    ) -> str: ...

    async def delete(self, *, key: str) -> None: ...


class LocalStorage:
    def __init__(self, base_dir: Path, url_prefix: str) -> None:
        self.base_dir = base_dir
        self.url_prefix = url_prefix.rstrip("/")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, *, key: str, content: bytes, content_type: str) -> str:
        target = self.base_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return f"{self.url_prefix}/{key}"

    async def delete(self, *, key: str) -> None:
        (self.base_dir / key).unlink(missing_ok=True)


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


MIME_EXTENSIONS: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
