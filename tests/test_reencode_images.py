from PIL import Image

from app.core.config import settings
from scripts.reencode_images import reencode_file, webp_url
from tests.factories import make_png


def test_reencodes_big_png_to_small_webp_next_to_it(tmp_path) -> None:
    source = tmp_path / "tile.png"
    source.write_bytes(make_png(3000, 2000))
    source.chmod(0o640)

    result = reencode_file(source, write=True)

    assert result.path == tmp_path / "tile.webp"
    assert source.exists()  # the original stays for rollback
    assert result.path.stat().st_mode & 0o777 == 0o640
    with Image.open(result.path) as image:
        assert image.format == "WEBP"
        assert max(image.size) == settings.IMAGE_MAX_DIMENSION


def test_dry_run_writes_nothing(tmp_path) -> None:
    source = tmp_path / "tile.png"
    source.write_bytes(make_png(40, 30))

    reencode_file(source, write=False)

    assert not (tmp_path / "tile.webp").exists()


def test_url_keeps_the_same_name_with_webp_extension() -> None:
    assert (
        webp_url("/uploads/treatment-focuses/a/b.png")
        == "/uploads/treatment-focuses/a/b.webp"
    )
