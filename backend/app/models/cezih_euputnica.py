import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseTenantModel


class CezihEUputnica(BaseTenantModel):
    """Persisted e-Uputnica (referral) fetched from CEZIH."""

    __tablename__ = "cezih_euputnice"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # External referral ID from CEZIH (e.g. "EU-2026-001")
    external_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    datum_izdavanja: Mapped[str] = mapped_column(String(20), nullable=False)
    izdavatelj: Mapped[str] = mapped_column(String(200), nullable=False)
    svrha: Mapped[str] = mapped_column(String(200), nullable=False)
    specijalist: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="Otvorena")
