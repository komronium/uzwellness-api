from pydantic import BaseModel, Field


class Translations(BaseModel):
    """Partial translations payload — used for PATCH (any subset of locales)."""

    uz: str | None = None
    ru: str | None = None
    en: str | None = None


class TranslationsCreate(BaseModel):
    """Required translations payload — used for POST (all 3 locales mandatory)."""

    uz: str = Field(min_length=1)
    ru: str = Field(min_length=1)
    en: str = Field(min_length=1)
