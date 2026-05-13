import uuid

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DtsCode(Base):
    """DTS (Dijagnosticko-Terapijski Postupci) procedure codes from CEZIH terminology.

    Global table, not tenant-scoped. Bootstrap from CodeSystem_DTS.json.
    """

    __tablename__ = "dts_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    display: Mapped[str] = mapped_column(String(500), nullable=False)
    system: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="http://fhir.cezih.hr/specifikacije/CodeSystem/DTS",
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="0.1.0")
    aktivan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    synced_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
