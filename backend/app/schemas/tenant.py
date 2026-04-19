from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TenantRead(BaseModel):
    id: UUID
    naziv: str
    vrsta: str
    email: str
    telefon: str | None
    adresa: str | None
    oib: str | None
    grad: str | None
    postanski_broj: str | None
    zupanija: str | None
    web: str | None
    sifra_ustanove: str | None
    oid: str | None
    plan_tier: str
    trial_expires_at: datetime | None
    is_active: bool
    cezih_status: str
    has_hzzo_contract: bool

    model_config = {"from_attributes": True}


class TenantUpdate(BaseModel):
    naziv: str | None = None
    vrsta: str | None = None
    email: str | None = None
    telefon: str | None = None
    adresa: str | None = None
    oib: str | None = None
    grad: str | None = None
    postanski_broj: str | None = None
    zupanija: str | None = None
    web: str | None = None
    sifra_ustanove: str | None = None
    has_hzzo_contract: bool | None = None
