import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

_DJELATNOST_RE = re.compile(r"^\d{7}$")


def _coerce_djelatnost_code(v: str | None) -> str | None:
    if v == "":
        return None
    if v is not None and not _DJELATNOST_RE.match(v):
        raise ValueError("Šifra djelatnosti mora imati točno 7 znamenki")
    return v


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
    djelatnost_code: str | None = None
    djelatnost_display: str | None = None
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
    djelatnost_code: str | None = None
    djelatnost_display: str | None = None
    has_hzzo_contract: bool | None = None

    _coerce_djelatnost_code = field_validator("djelatnost_code", mode="before")(_coerce_djelatnost_code)
