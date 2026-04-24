import re

from pydantic import BaseModel, EmailStr, field_validator

from app.schemas.user import UserReadWithTenant


def _validate_password_strength(password: str) -> str:
    """Enforce password complexity for medical data protection (GDPR Article 32)."""
    if len(password) < 8:
        raise ValueError("Lozinka mora imati najmanje 8 znakova")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Lozinka mora sadržavati barem jedno veliko slovo")
    if not re.search(r"[a-z]", password):
        raise ValueError("Lozinka mora sadržavati barem jedno malo slovo")
    if not re.search(r"\d", password):
        raise ValueError("Lozinka mora sadržavati barem jedan broj")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]", password):
        raise ValueError("Lozinka mora sadržavati barem jedan posebni znak")
    return password


class RegisterRequest(BaseModel):
    naziv_klinike: str
    vrsta: str = "ordinacija"
    email: EmailStr
    password: str
    ime: str
    prezime: str
    terms_accepted: bool

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)

    @field_validator("terms_accepted")
    @classmethod
    def validate_terms_accepted(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Morate prihvatiti Uvjete korištenja i Pravila privatnosti")
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
    requires_terms_acceptance: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_strength(v)
