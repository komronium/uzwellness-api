import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

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
    transfer_commission_percent: Decimal | None = Field(
        default=None, ge=0, le=100, decimal_places=2
    )

    @model_validator(mode="after")
    def _validate(self):
        if (
            self.role == UserRole.TRANSFER_ADMIN
            and self.transfer_commission_percent is None
        ):
            raise ValueError(
                "transfer_commission_percent is required for the transfer_admin role"
            )
        return self


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    role: UserRole | None = None
    is_active: bool | None = None
    sanatorium_id: uuid.UUID | None = None
    transfer_commission_percent: Decimal | None = Field(
        default=None, ge=0, le=100, decimal_places=2
    )


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: UserRole
    is_active: bool
    sanatorium_id: uuid.UUID | None = None
    transfer_commission_percent: Decimal | None = None
    created_at: datetime


class UserList(Page[UserRead]):
    pass
