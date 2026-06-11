"""Unit tests for slugify (no DB)."""

from app.core.slug import slugify


class TestSlugify:
    def test_simple_lowercase(self):
        assert slugify("Hello World") == "hello-world"

    def test_strips_uzbek_apostrophes(self):
        assert slugify("Oʻzbekiston") == "ozbekiston"

    def test_strips_curly_quotes(self):
        assert slugify("It’s great") == "its-great"

    def test_collapses_whitespace(self):
        assert slugify("  too   much   space  ") == "too-much-space"

    def test_strips_punctuation(self):
        assert slugify("Hello, World!") == "hello-world"

    def test_strips_diacritics(self):
        assert slugify("Café Niño") == "cafe-nino"

    def test_empty_returns_fallback(self):
        assert slugify("") == "item"
        assert slugify("!!!") == "item"

    def test_custom_fallback(self):
        assert slugify("", fallback="sanatorium") == "sanatorium"

    def test_numeric_preserved(self):
        assert slugify("Hotel 5 Stars") == "hotel-5-stars"

    def test_strips_leading_trailing_dashes(self):
        assert slugify("--hello--") == "hello"
