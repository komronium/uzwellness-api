from io import BytesIO

from fastapi import HTTPException, status
from PIL import Image, ImageOps, UnidentifiedImageError
from PIL.Image import DecompressionBombError

from app.core.config import settings

WEBP_MIME = "image/webp"


def to_webp(content: bytes) -> tuple[bytes, str]:
    try:
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > settings.IMAGE_MAX_PIXELS:
                megapixels = settings.IMAGE_MAX_PIXELS / 1_000_000
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=(
                        f"This image is {image.width}×{image.height} pixels. "
                        f"Please upload one under {megapixels:.0f} megapixels "
                        f"({settings.IMAGE_MAX_DIMENSION} px on the long side "
                        "is plenty)."
                    ),
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
    except DecompressionBombError as exc:
        # Pillow's own bomb guard fires before ours on a crafted header, and it
        # is not an OSError — without this branch it escapes as a 500.
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                "This image claims a pixel count large enough to exhaust the "
                "server's memory and was rejected. Please upload a normal photo."
            ),
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "This file could not be read as an image. "
                "Please upload a JPEG, PNG or WebP photo."
            ),
        ) from exc
    return output.getvalue(), WEBP_MIME


def _webp_mode(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "RGB"}:
        return image
    if "A" in image.getbands() or image.mode == "P":
        return image.convert("RGBA")
    return image.convert("RGB")
