from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentRead(BaseModel):
    id: UUID
    patient_id: UUID
    naziv: str
    kategorija: str
    file_size: int
    mime_type: str
    uploaded_by: UUID
    cezih_reference_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    id: UUID
    patient_id: UUID
    naziv: str
    kategorija: str
    file_size: int
    mime_type: str
    uploaded_by: UUID
    cezih_reference_id: str | None = None
    created_at: datetime
