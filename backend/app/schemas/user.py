from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.schemas.tenant import TenantRead

CezihSigningMethod = Literal["smartcard", "extsigner"]


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
    cezih_signing_method: CezihSigningMethod = "extsigner"


class UserUpdate(BaseModel):
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
    cezih_signing_method: CezihSigningMethod | None = None
    """None on UserUpdate means 'do not change'; NULL values are no longer accepted."""


class CardBindingRequest(BaseModel):
    card_holder_name: str
    card_certificate_oib: str | None = None
