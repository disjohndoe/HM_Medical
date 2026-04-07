import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BaseTenantModel


class PredracunCounter(Base):
    __tablename__ = "predracun_counters"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), primary_key=True
    )
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    next_seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")


class Predracun(BaseTenantModel):
    __tablename__ = "predracuni"
    __table_args__ = (
        UniqueConstraint("tenant_id", "broj", name="uq_predracun_broj_tenant"),
        Index("ix_predracuni_patient", "tenant_id", "patient_id", "datum"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    broj: Mapped[str] = mapped_column(String(20), nullable=False)
    datum: Mapped[date] = mapped_column(Date, nullable=False)
    ukupno_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    napomena: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)


class PredracunStavka(Base):
    __tablename__ = "predracun_stavke"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    predracun_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("predracuni.id", ondelete="CASCADE"), nullable=False
    )
    performed_procedure_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("performed_procedures.id"), nullable=True
    )
    sifra: Mapped[str] = mapped_column(String(20), nullable=False)
    naziv: Mapped[str] = mapped_column(String(255), nullable=False)
    datum: Mapped[date] = mapped_column(Date, nullable=False)
    cijena_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
