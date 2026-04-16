import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseTenantModel


class User(BaseTenantModel):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'doctor', 'nurse', 'receptionist')", name="ck_user_role"),
        CheckConstraint(
            "cezih_signing_method IS NULL OR cezih_signing_method IN ('smartcard', 'extsigner')",
            name="ck_user_cezih_signing_method",
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
    cezih_signing_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
