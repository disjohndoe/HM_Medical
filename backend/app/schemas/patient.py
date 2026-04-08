from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.utils.croatian import validate_mbo, validate_oib


class PatientCreate(BaseModel):
    ime: str
    prezime: str
    datum_rodjenja: date | None = None
    spol: str | None = None
    oib: str | None = None
    mbo: str | None = None
    adresa: str | None = None
    grad: str | None = None
    postanski_broj: str | None = None
    telefon: str | None = None
    mobitel: str | None = None
    email: str | None = None
    napomena: str | None = None
    alergije: str | None = None

    @field_validator("oib")
    @classmethod
    def validate_oib_field(cls, v: str | None) -> str | None:
        if v is not None and not validate_oib(v):
            raise ValueError("Neispravan OIB")
        return v

    @field_validator("mbo")
    @classmethod
    def validate_mbo_field(cls, v: str | None) -> str | None:
        if v is not None and not validate_mbo(v):
            raise ValueError("Neispravan MBO")
        return v

    @field_validator("spol")
    @classmethod
    def validate_spol(cls, v: str | None) -> str | None:
        if v is not None and v.upper() not in ("M", "Z"):
            raise ValueError("Spol mora biti M ili Z")
        return v.upper() if v else None


class PatientRead(BaseModel):
    id: UUID
    ime: str
    prezime: str
    datum_rodjenja: date | None
    spol: str | None
    oib: str | None
    mbo: str | None
    adresa: str | None
    grad: str | None
    postanski_broj: str | None
    telefon: str | None
    mobitel: str | None
    email: str | None
    napomena: str | None
    alergije: str | None
    is_active: bool
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime
    cezih_insurance_status: str | None = None
    cezih_insurance_checked_at: datetime | None = None

    model_config = {"from_attributes": True}


class PatientUpdate(BaseModel):
    ime: str | None = None
    prezime: str | None = None
    datum_rodjenja: date | None = None
    spol: str | None = None
    oib: str | None = None
    mbo: str | None = None
    adresa: str | None = None
    grad: str | None = None
    postanski_broj: str | None = None
    telefon: str | None = None
    mobitel: str | None = None
    email: str | None = None
    napomena: str | None = None
    alergije: str | None = None
    is_active: bool | None = None

    @field_validator("spol")
    @classmethod
    def validate_spol(cls, v: str | None) -> str | None:
        if v is not None and v.upper() not in ("M", "Z"):
            raise ValueError("Spol mora biti M ili Z")
        return v.upper() if v else None
