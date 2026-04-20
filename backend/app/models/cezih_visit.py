import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseTenantModel


class CezihVisit(BaseTenantModel):
    """Persisted CEZIH visit (Encounter) for tracking.

    Used as a short-lived local mirror so freshly-created visits stay visible
    in the UI even while CEZIH's QEDm read side is still catching up. The
    list endpoint merges these rows with the live CEZIH response for a few
    minutes after create.
    """

    __tablename__ = "cezih_visits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cezih_visit_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True,
        comment="CEZIH-assigned visit identifier",
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True,
    )
    patient_mbo: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="in-progress",
    )
    admission_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    tip_posjete: Mapped[str | None] = mapped_column(String(10), nullable=True)
    vrsta_posjete: Mapped[str | None] = mapped_column(String(10), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    diagnosis_case_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error_display: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_diagnostics: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
