import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.document import Document
from app.models.patient import Patient
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

    patient = await db.get(Patient, patient_id)
    if not patient or patient.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Pacijent nije pronađen")

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
        uploaded_by=doc.uploaded_by,
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

    file_path = Path(doc.file_path)

    await db.delete(doc)
    await db.flush()

    # Remove file from disk AFTER DB delete succeeds
    if file_path.exists():
        file_path.unlink(missing_ok=True)


class ImportCezihDocumentRequest(BaseModel):
    patient_id: uuid.UUID
    cezih_reference_id: str
    content_url: str
    naziv: str


@router.post("/import-cezih", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def import_cezih_document(
    request: Request,
    data: ImportCezihDocumentRequest,
    current_user: User = Depends(require_roles("admin", "doctor", "nurse")),
    db: AsyncSession = Depends(get_db),
):
    patient = await db.get(Patient, data.patient_id)
    if not patient or patient.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Pacijent nije pronađen")

    existing = await db.execute(
        select(Document).where(
            Document.tenant_id == current_user.tenant_id,
            Document.cezih_reference_id == data.cezih_reference_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Dokument je već spremljen")

    from app.core.plan_enforcement import check_cezih_access
    from app.services.cezih import dispatcher as cezih

    await check_cezih_access(db, current_user.tenant_id)
    content = await cezih.dispatch_retrieve_document(
        data.cezih_reference_id,
        document_url=data.content_url,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=request.app.state.http_client,
    )

    if not content.startswith(b"%PDF"):
        from app.services.pdf_generator import cezih_text_to_pdf
        text = content.decode("utf-8", errors="replace")
        content = cezih_text_to_pdf(text)

    upload_dir = Path(settings.UPLOAD_DIR) / str(current_user.tenant_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4()
    file_path = upload_dir / f"{file_id}.pdf"
    with open(file_path, "wb") as f:
        f.write(content)

    doc = Document(
        tenant_id=current_user.tenant_id,
        patient_id=data.patient_id,
        naziv=sanitize_filename(data.naziv),
        kategorija="nalaz",
        file_path=str(file_path),
        file_size=len(content),
        mime_type="application/pdf",
        uploaded_by=current_user.id,
        cezih_reference_id=data.cezih_reference_id,
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
        uploaded_by=doc.uploaded_by,
        cezih_reference_id=doc.cezih_reference_id,
        created_at=doc.created_at,
    )
