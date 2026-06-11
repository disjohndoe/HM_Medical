import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("vrsta IN ('ordinacija', 'poliklinika', 'dom_zdravlja')", name="ck_tenant_vrsta"),
        CheckConstraint(
            "cezih_status IN ('nepovezano', 'u_pripremi', 'testirano', 'certificirano')",
            name="ck_tenant_cezih_status",
        ),
        CheckConstraint(
            "plan_tier IN ('trial', 'solo', 'poliklinika', 'poliklinika_plus')",
            name="ck_tenant_plan_tier",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    naziv: Mapped[str] = mapped_column(String(255), nullable=False)
    vrsta: Mapped[str] = mapped_column(String(50), nullable=False, server_default="ordinacija")
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    telefon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    adresa: Mapped[str | None] = mapped_column(Text, nullable=True)
    oib: Mapped[str | None] = mapped_column(String(11), nullable=True, unique=True)
    grad: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postanski_broj: Mapped[str | None] = mapped_column(String(10), nullable=True)
    zupanija: Mapped[str | None] = mapped_column(String(100), nullable=True)
    web: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sifra_ustanove: Mapped[str | None] = mapped_column(String(20), nullable=True)
    oid: Mapped[str | None] = mapped_column(String(50), nullable=True)
    djelatnost_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    djelatnost_display: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plan_tier: Mapped[str] = mapped_column(String(20), nullable=False, server_default="trial")
    trial_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    cezih_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="nepovezano")
    agent_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    has_hzzo_contract: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
