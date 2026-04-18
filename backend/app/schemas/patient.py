import re
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.utils.croatian import validate_mbo, validate_oib

_PUTOVNICA_RE = re.compile(r"^[A-Za-z0-9]{5,50}$")
_EHIC_RE = re.compile(r"^[0-9A-Za-z]{20}$")
_DRZAVLJANSTVO_RE = re.compile(r"^[A-Za-z]{2,3}$")


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
    broj_putovnice: str | None = None
    ehic_broj: str | None = None
    cezih_patient_id: str | None = None
    drzavljanstvo: str | None = None
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
    broj_putovnice: str | None = None
    ehic_broj: str | None = None
    cezih_patient_id: str | None = None
    drzavljanstvo: str | None = None
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

    @field_validator("broj_putovnice")
    @classmethod
    def validate_putovnica(cls, v: str | None) -> str | None:
        if v is not None and v != "" and not _PUTOVNICA_RE.match(v):
            raise ValueError("Broj putovnice mora imati 5-50 alfanumeričkih znakova")
        return v

    @field_validator("ehic_broj")
    @classmethod
    def validate_ehic(cls, v: str | None) -> str | None:
        if v is not None and v != "" and not _EHIC_RE.match(v):
            raise ValueError("EHIC broj mora imati točno 20 alfanumeričkih znakova")
        return v

    @field_validator("drzavljanstvo")
    @classmethod
    def validate_drzavljanstvo(cls, v: str | None) -> str | None:
        if v is not None and v != "" and not _DRZAVLJANSTVO_RE.match(v):
            raise ValueError("Državljanstvo mora biti ISO-3166 kod (2 ili 3 slova)")
        return v.upper() if v else v
