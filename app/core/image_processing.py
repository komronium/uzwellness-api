from io import BytesIO

from fastapi import HTTPException, status
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings

WEBP_MIME = "image/webp"


def to_webp(content: bytes) -> tuple[bytes, str]:
    try:
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > settings.IMAGE_MAX_PIXELS:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Image dimensions are too large",
                )
            image = ImageOps.exif_transpose(image)
            image.thumbnail(
                (settings.IMAGE_MAX_DIMENSION, settings.IMAGE_MAX_DIMENSION),
                Image.Resampling.LANCZOS,
            )
            image = _webp_mode(image)
            output = BytesIO()
            image.save(
                output, format="WEBP", quality=settings.IMAGE_WEBP_QUALITY, method=6
            )
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Invalid image file",
        ) from exc
    return output.getvalue(), WEBP_MIME


def _webp_mode(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "RGB"}:
        return image
    if "A" in image.getbands() or image.mode == "P":
        return image.convert("RGBA")
    return image.convert("RGB")
