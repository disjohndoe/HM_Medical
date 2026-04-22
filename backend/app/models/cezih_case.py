import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseTenantModel


class CezihCase(BaseTenantModel):
    """Persisted CEZIH case (Condition/EpisodeOfCare) for tracking."""

    __tablename__ = "cezih_cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cezih_case_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="CEZIH-assigned global case identifier",
    )
    local_case_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Our local case identifier sent in create message",
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
    )
    patient_mbo: Mapped[str] = mapped_column(String(50), nullable=False)
    icd_code: Mapped[str] = mapped_column(String(20), nullable=False)
    icd_display: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    clinical_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="active, remission, relapse, resolved",
    )
    verification_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="unconfirmed",
    )
    onset_date: Mapped[str] = mapped_column(String(20), nullable=False)
    abatement_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error_display: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_diagnostics: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
