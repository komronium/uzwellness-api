from dataclasses import dataclass

from pydantic import BaseModel, EmailStr, Field, model_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
    confirm_new_password: str

    @model_validator(mode="after")
    def _check_match(self) -> "ChangePasswordRequest":
        if self.new_password != self.confirm_new_password:
            raise ValueError("new_password and confirm_new_password do not match")
        if self.new_password == self.current_password:
            raise ValueError("new_password must differ from current_password")
        return self


class Token(BaseModel):
    """Public login/refresh response — refresh lives in an HttpOnly cookie."""

    access_token: str
    token_type: str = "bearer"


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    """Access + refresh pair produced by AuthService before the cookie is set."""

    access_token: str
    refresh_token: str
