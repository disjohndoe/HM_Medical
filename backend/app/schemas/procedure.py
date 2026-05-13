from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, field_validator


class ProcedureCreate(BaseModel):
    dts_code: str
    cijena_cents: int = 0
    trajanje_minuta: int = 30

    @field_validator("cijena_cents")
    @classmethod
    def validate_cijena(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Cijena ne može biti negativna")
        return v

    @field_validator("trajanje_minuta")
    @classmethod
    def validate_trajanje(cls, v: int) -> int:
        if v < 5 or v > 480:
            raise ValueError("Trajanje mora biti između 5 i 480 minuta")
        return v


class ProcedureRead(BaseModel):
    id: UUID
    sifra: str
    naziv: str
    opis: str | None
    cijena_cents: int
    trajanje_minuta: int
    kategorija: str
    is_active: bool
    tenant_id: UUID
    dts_code: str | None = None
    dts_display: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProcedureUpdate(BaseModel):
    cijena_cents: int | None = None
    trajanje_minuta: int | None = None
    is_active: bool | None = None

    @field_validator("trajanje_minuta")
    @classmethod
    def validate_trajanje(cls, v: int | None) -> int | None:
        if v is not None and (v < 5 or v > 480):
            raise ValueError("Trajanje mora biti između 5 i 480 minuta")
        return v

    @field_validator("cijena_cents")
    @classmethod
    def validate_cijena(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("Cijena ne može biti negativna")
        return v


class PerformedProcedureCreate(BaseModel):
    patient_id: UUID
    procedure_id: UUID
    appointment_id: UUID | None = None
    medical_record_id: UUID | None = None
    lokacija: str | None = None
    datum: date
    cijena_cents: int | None = None
    napomena: str | None = None


class PerformedProcedureRead(BaseModel):
    id: UUID
    patient_id: UUID
    appointment_id: UUID | None
    medical_record_id: UUID | None = None
    procedure_id: UUID
    doktor_id: UUID
    lokacija: str | None
    datum: date
    cijena_cents: int
    napomena: str | None
    procedure_naziv: str | None = None
    procedure_sifra: str | None = None
    dts_code: str | None = None
    doktor_ime: str | None = None
    doktor_prezime: str | None = None
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
