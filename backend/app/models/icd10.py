import uuid

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Icd10Code(Base):
    """ICD-10 HR (MKB-10) diagnosis codes — synced from CEZIH terminology service.

    Global table, not tenant-scoped. Bootstrap from Simplifier package,
    monthly sync from CEZIH ValueSet/$expand.
    """

    __tablename__ = "icd10_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    display: Mapped[str] = mapped_column(String(500), nullable=False)
    system: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr",
    )
    aktivan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    synced_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Lowercase composite for ILIKE search
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
