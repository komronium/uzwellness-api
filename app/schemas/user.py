import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole
from app.schemas.common import Page


class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserAdminCreate(UserCreate):
    role: UserRole = UserRole.CUSTOMER
    sanatorium_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    role: UserRole | None = None
    is_active: bool | None = None
    sanatorium_id: uuid.UUID | None = None


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: UserRole
    is_active: bool
    sanatorium_id: uuid.UUID | None = None
    created_at: datetime


class UserList(Page[UserRead]):
    pass
