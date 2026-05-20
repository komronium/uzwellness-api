from pydantic import BaseModel, Field


class Translations(BaseModel):
    uz: str | None = None
    ru: str | None = None
    en: str | None = None


class TranslationsCreate(BaseModel):
    uz: str = Field(min_length=1)
    ru: str = Field(min_length=1)
    en: str = Field(min_length=1)
