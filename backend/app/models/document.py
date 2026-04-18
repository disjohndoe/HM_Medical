import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseTenantModel


class Document(BaseTenantModel):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "kategorija IN ('nalaz', 'snimka', 'dokument', 'ostalo')",
            name="ck_document_kategorija",
        ),
        Index("ix_documents_tenant_patient", "tenant_id", "patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    naziv: Mapped[str] = mapped_column(String(255), nullable=False)
    kategorija: Mapped[str] = mapped_column(String(50), nullable=False, server_default="ostalo")
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    cezih_reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
