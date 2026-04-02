from pydantic import BaseModel, EmailStr, field_validator

from app.schemas.user import UserReadWithTenant


class RegisterRequest(BaseModel):
    naziv_klinike: str
    vrsta: str = "ordinacija"
    email: EmailStr
    password: str
    ime: str
    prezime: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Lozinka mora imati najmanje 8 znakova")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserReadWithTenant | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Lozinka mora imati najmanje 8 znakova")
        return v
