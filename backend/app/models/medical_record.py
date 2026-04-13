import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseTenantModel


class MedicalRecord(BaseTenantModel):
    __tablename__ = "medical_records"
    __table_args__ = (
        Index("ix_medical_records_patient", "tenant_id", "patient_id", "datum"),
        CheckConstraint("sensitivity IN ('standard', 'nursing', 'restricted')", name="ck_record_sensitivity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    doktor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True
    )
    datum: Mapped[date] = mapped_column(Date, nullable=False)
    tip: Mapped[str] = mapped_column(String(30), nullable=False)
    dijagnoza_mkb: Mapped[str | None] = mapped_column(String(10), nullable=True)
    dijagnoza_tekst: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sadrzaj: Mapped[str] = mapped_column(Text, nullable=False)
    cezih_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    cezih_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cezih_reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cezih_storno: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    cezih_encounter_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cezih_case_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cezih_signature_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    cezih_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sensitivity: Mapped[str] = mapped_column(String(20), nullable=False, server_default="standard")
    preporucena_terapija: Mapped[list | None] = mapped_column(JSON, nullable=True)
