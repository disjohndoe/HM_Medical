import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseTenantModel


class MedicalRecord(BaseTenantModel):
    __tablename__ = "medical_records"
    __table_args__ = (
        Index("ix_medical_records_patient", "tenant_id", "patient_id", "datum"),
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
