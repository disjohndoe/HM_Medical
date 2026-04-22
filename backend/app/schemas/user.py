import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator

from app.schemas.tenant import TenantRead

CezihSigningMethod = Literal["smartcard", "extsigner"]

_HZJZ_RE = re.compile(r"^\d{7}$")
_MBO_RE = re.compile(r"^\d{9}$")


def _coerce_practitioner_id(v: str | None) -> str | None:
    if v == "":
        return None
    if v is not None and not _HZJZ_RE.match(v):
        raise ValueError("HZJZ broj mora imati točno 7 znamenki")
    return v


def _coerce_mbo_lijecnika(v: str | None) -> str | None:
    if v == "":
        return None
    if v is not None and not _MBO_RE.match(v):
        raise ValueError("MBO liječnika mora imati točno 9 znamenki")
    return v


class UserRead(BaseModel):
    id: UUID
    email: str
    ime: str
    prezime: str
    titula: str | None
    telefon: str | None
    role: str
    is_active: bool
    last_login_at: datetime | None
    tenant_id: UUID
    created_at: datetime
    card_holder_name: str | None = None
    card_certificate_oib: str | None = None
    card_certificate_serial: str | None = None
    card_required: bool = False
    practitioner_id: str | None = None
    mbo_lijecnika: str | None = None
    cezih_signing_method: CezihSigningMethod

    model_config = {"from_attributes": True}


class UserReadWithTenant(UserRead):
    tenant: TenantRead


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    ime: str
    prezime: str
    titula: str | None = None
    telefon: str | None = None
    role: str = "doctor"
    practitioner_id: str | None = None
    mbo_lijecnika: str | None = None
    cezih_signing_method: CezihSigningMethod = "extsigner"

    _coerce_practitioner_id = field_validator("practitioner_id", mode="before")(_coerce_practitioner_id)
    _coerce_mbo_lijecnika = field_validator("mbo_lijecnika", mode="before")(_coerce_mbo_lijecnika)


class UserUpdate(BaseModel):
    """Partial user update. Omit a field to leave it unchanged.

    cezih_signing_method: explicit `null` is rejected — omit the key to preserve the
    current value. Other nullable fields (practitioner_id, mbo_lijecnika, titula, ...)
    accept `null` to clear them.
    """

    email: EmailStr | None = None
    ime: str | None = None
    prezime: str | None = None
    titula: str | None = None
    telefon: str | None = None
    role: str | None = None
    is_active: bool | None = None
    card_holder_name: str | None = None
    card_certificate_oib: str | None = None
    card_required: bool | None = None
    practitioner_id: str | None = None
    mbo_lijecnika: str | None = None
    cezih_signing_method: CezihSigningMethod | None = None

    _coerce_practitioner_id = field_validator("practitioner_id", mode="before")(_coerce_practitioner_id)
    _coerce_mbo_lijecnika = field_validator("mbo_lijecnika", mode="before")(_coerce_mbo_lijecnika)

    @field_validator("cezih_signing_method")
    @classmethod
    def reject_explicit_null_signing_method(cls, v: CezihSigningMethod | None) -> CezihSigningMethod | None:
        if v is None:
            raise ValueError("cezih_signing_method ne smije biti null; izostavite polje da ga ne mijenjate")
        return v


class CardBindingRequest(BaseModel):
    card_holder_name: str
    card_certificate_oib: str | None = None
