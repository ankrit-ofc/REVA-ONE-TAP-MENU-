from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str
    restaurant_slug: str
    remember_me: bool = False

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v

    @field_validator("restaurant_slug")
    @classmethod
    def slug_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("restaurant_slug must not be empty")
        return v.strip()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    restaurant_slug: str

    @field_validator("restaurant_slug")
    @classmethod
    def slug_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("restaurant_slug must not be empty")
        return v.strip()


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    message: str
