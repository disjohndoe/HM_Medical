import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentRead, DocumentUploadResponse

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "application/pdf",
}
ALLOWED_EXTENSIONS = {".jpeg", ".jpg", ".png", ".pdf"}


def sanitize_filename(filename: str) -> str:
    """Strip path traversal, control chars, and dangerous patterns from filenames."""
    filename = filename.replace("/", "").replace("\\", "")
    filename = re.sub(r"[\x00-\x1f\x7f]", "", filename)
    filename = filename.lstrip(".-")[:255]
    return filename or "unnamed"


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    patient_id: uuid.UUID = Form(...),
    kategorija: str = Form("ostalo"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if kategorija not in ("nalaz", "snimka", "dokument", "ostalo"):
        raise HTTPException(status_code=400, detail="Nevažeća kategorija dokumenta")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Naziv datoteke je obavezan")

    # Validate extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Dopuštene vrste datoteka: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Datoteka je prevelika (maks {settings.MAX_UPLOAD_SIZE_MB} MB)",
        )

    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in ALLOWED_MIME_TYPES and ext != ".pdf":
        raise HTTPException(status_code=400, detail="Nevažeća vrsta datoteke")

    # Save to disk
    upload_dir = Path(settings.UPLOAD_DIR) / str(current_user.tenant_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4()
    safe_filename = f"{file_id}{ext}"
    file_path = upload_dir / safe_filename

    with open(file_path, "wb") as f:
        f.write(content)

    doc = Document(
        tenant_id=current_user.tenant_id,
        patient_id=patient_id,
        naziv=sanitize_filename(file.filename),
        kategorija=kategorija,
        file_path=str(file_path),
        file_size=len(content),
        mime_type=mime_type,
        uploaded_by=current_user.id,
    )
    db.add(doc)
    await db.flush()

    return DocumentUploadResponse(
        id=doc.id,
        patient_id=doc.patient_id,
        naziv=doc.naziv,
        kategorija=doc.kategorija,
        file_size=doc.file_size,
        mime_type=doc.mime_type,
        created_at=doc.created_at,
    )


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    patient_id: uuid.UUID | None = Query(None),
    kategorija: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Document).where(Document.tenant_id == current_user.tenant_id)
    if patient_id:
        q = q.where(Document.patient_id == patient_id)
    if kategorija:
        q = q.where(Document.kategorija == kategorija)
    q = q.order_by(Document.created_at.desc())

    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, document_id)
    if not doc or doc.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Dokument nije pronađen")

    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Datoteka nije pronađena na disku")

    from fastapi.responses import FileResponse

    return FileResponse(
        path=str(file_path),
        media_type=doc.mime_type,
        filename=sanitize_filename(doc.naziv),
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, document_id)
    if not doc or doc.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Dokument nije pronađen")

    # Remove file from disk
    file_path = Path(doc.file_path)
    if file_path.exists():
        file_path.unlink()

    await db.delete(doc)
    await db.flush()
