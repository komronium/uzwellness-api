from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Standard paginated list response; subclass as `class XyzList(Page[XyzRead])`."""

    items: list[T]
    total: int
    limit: int
    offset: int


class Translations(BaseModel):
    uz: str | None = None
    ru: str | None = None
    en: str | None = None


class TranslationsCreate(BaseModel):
    uz: str = Field(min_length=1)
    ru: str = Field(min_length=1)
    en: str = Field(min_length=1)


class ErrorResponse(BaseModel):
    detail: str | list | dict
