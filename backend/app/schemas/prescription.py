from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class PrescriptionLijekEntry(BaseModel):
    atk: str = ""
    naziv: str
    oblik: str = ""
    jacina: str = ""
    kolicina: int = 1
    doziranje: str = ""
    napomena: str = ""


class PrescriptionCreate(BaseModel):
    patient_id: UUID
    medical_record_id: UUID | None = None
    lijekovi: list[PrescriptionLijekEntry]
    napomena: str | None = None


class PrescriptionUpdate(BaseModel):
    lijekovi: list[PrescriptionLijekEntry] | None = None
    napomena: str | None = None


class PrescriptionRead(BaseModel):
    id: UUID
    patient_id: UUID
    doktor_id: UUID
    medical_record_id: UUID | None
    lijekovi: list[PrescriptionLijekEntry]
    cezih_sent: bool
    cezih_sent_at: datetime | None
    cezih_recept_id: str | None
    cezih_storno: bool
    cezih_storno_at: datetime | None
    napomena: str | None
    doktor_ime: str | None = None
    doktor_prezime: str | None = None
    medical_record_datum: date | None = None
    medical_record_tip: str | None = None
    medical_record_dijagnoza_tekst: str | None = None
    medical_record_dijagnoza_mkb: str | None = None
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PrescriptionSendResponse(BaseModel):
    prescription_id: UUID
    cezih_recept_id: str
    success: bool
