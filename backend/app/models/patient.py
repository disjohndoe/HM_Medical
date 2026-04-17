import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseTenantModel


class Patient(BaseTenantModel):
    __tablename__ = "patients"
    __table_args__ = (
        CheckConstraint("spol IN ('M', 'Z')", name="ck_patient_spol"),
        UniqueConstraint("tenant_id", "oib", name="uq_patient_tenant_oib"),
        UniqueConstraint("tenant_id", "mbo", name="uq_patient_tenant_mbo"),
        UniqueConstraint("tenant_id", "cezih_patient_id", name="uq_patient_tenant_cezih_id"),
        Index("ix_patient_tenant_prezime", "tenant_id", "prezime"),
        Index("ix_patient_tenant_cezih_id", "tenant_id", "cezih_patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ime: Mapped[str] = mapped_column(String(100), nullable=False)
    prezime: Mapped[str] = mapped_column(String(100), nullable=False)
    datum_rodjenja: Mapped[date | None] = mapped_column(Date, nullable=True)
    spol: Mapped[str | None] = mapped_column(String(1), nullable=True)
    oib: Mapped[str | None] = mapped_column(String(11), nullable=True)
    mbo: Mapped[str | None] = mapped_column(String(9), nullable=True)
    # Foreign patient identifiers (populated by PMIR registration for non-insured)
    broj_putovnice: Mapped[str | None] = mapped_column(String(15), nullable=True)
    ehic_broj: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cezih_patient_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    drzavljanstvo: Mapped[str | None] = mapped_column(String(3), nullable=True)
    adresa: Mapped[str | None] = mapped_column(String(255), nullable=True)
    grad: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postanski_broj: Mapped[str | None] = mapped_column(String(10), nullable=True)
    telefon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mobitel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    napomena: Mapped[str | None] = mapped_column(Text, nullable=True)
    alergije: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # CEZIH insurance sync
    cezih_insurance_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cezih_insurance_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
