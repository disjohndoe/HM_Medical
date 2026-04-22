import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseTenantModel


class Procedure(BaseTenantModel):
    __tablename__ = "procedures"
    __table_args__ = (UniqueConstraint("tenant_id", "sifra", name="uq_procedure_tenant_sifra"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sifra: Mapped[str] = mapped_column(String(20), nullable=False)
    naziv: Mapped[str] = mapped_column(String(255), nullable=False)
    opis: Mapped[str | None] = mapped_column(Text, nullable=True)
    cijena_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    trajanje_minuta: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    kategorija: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class PerformedProcedure(BaseTenantModel):
    __tablename__ = "performed_procedures"
    __table_args__ = (Index("ix_performed_procedures_patient", "tenant_id", "patient_id", "datum"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True
    )
    medical_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medical_records.id"), nullable=True
    )
    procedure_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("procedures.id"), nullable=False)
    doktor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    lokacija: Mapped[str | None] = mapped_column(String(100), nullable=True)
    datum: Mapped[date] = mapped_column(Date, nullable=False)
    cijena_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    napomena: Mapped[str | None] = mapped_column(Text, nullable=True)
