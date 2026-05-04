import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseTenantModel


class User(BaseTenantModel):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'doctor', 'nurse', 'receptionist')", name="ck_user_role"),
        CheckConstraint(
            "cezih_signing_method IN ('smartcard', 'extsigner')",
            name="ck_user_cezih_signing_method",
        ),
        CheckConstraint(
            "role IN ('doctor','admin','nurse') OR (practitioner_id IS NULL AND mbo_lijecnika IS NULL)",
            name="ck_user_role_can_hold_doctor_ids",
        ),
        Index(
            "ux_users_tenant_practitioner_id",
            "tenant_id",
            "practitioner_id",
            unique=True,
            postgresql_where=text("practitioner_id IS NOT NULL"),
        ),
        Index(
            "ux_users_tenant_mbo_lijecnika",
            "tenant_id",
            "mbo_lijecnika",
            unique=True,
            postgresql_where=text("mbo_lijecnika IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    ime: Mapped[str] = mapped_column(String(100), nullable=False)
    prezime: Mapped[str] = mapped_column(String(100), nullable=False)
    titula: Mapped[str | None] = mapped_column(String(50), nullable=True)
    telefon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="doctor")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    card_holder_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    card_certificate_oib: Mapped[str | None] = mapped_column(String(11), nullable=True)
    card_certificate_serial: Mapped[str | None] = mapped_column(String(128), nullable=True)
    card_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    practitioner_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mbo_lijecnika: Mapped[str | None] = mapped_column(String(9), nullable=True)
    cezih_signing_method: Mapped[str] = mapped_column(String(20), nullable=False, server_default="extsigner")
    djelatnost_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    djelatnost_display: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terms_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
