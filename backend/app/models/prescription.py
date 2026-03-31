import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseTenantModel


class Prescription(BaseTenantModel):
    __tablename__ = "prescriptions"
    __table_args__ = (
        Index("ix_prescriptions_patient", "tenant_id", "patient_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    doktor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    medical_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medical_records.id"), nullable=True
    )

    # Drug data as JSONB array of {atk, naziv, oblik, jacina, kolicina, doziranje, napomena}
    lijekovi: Mapped[list] = mapped_column(JSONB, nullable=False)

    # CEZIH lifecycle
    cezih_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    cezih_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cezih_recept_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    cezih_storno: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    cezih_storno_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    napomena: Mapped[str | None] = mapped_column(Text, nullable=True)
