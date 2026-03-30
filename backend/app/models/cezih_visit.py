import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseTenantModel


class CezihVisit(BaseTenantModel):
    """Persisted CEZIH visit (Encounter) for tracking."""

    __tablename__ = "cezih_visits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cezih_visit_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True,
        comment="CEZIH-assigned visit identifier (identifikator-posjete)",
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True,
    )
    patient_mbo: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="in-progress",
        comment="in-progress, finished, entered-in-error",
    )
    admission_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    diagnosis_case_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="CEZIH case identifier linked at close",
    )
