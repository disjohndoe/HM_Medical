import uuid
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.patient import Patient
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.predracun import PredracunCreate, PredracunRead
from app.services import predracun_service
from app.services.pdf_generator import PredracunPDFGenerator
from app.utils.pagination import PaginatedResponse

router = APIRouter(tags=["predracuni"])


def _tenant_dict(tenant: Tenant) -> dict:
    return {
        "naziv": tenant.naziv,
        "vrsta": tenant.vrsta,
        "adresa": tenant.adresa,
        "grad": tenant.grad,
        "postanski_broj": tenant.postanski_broj,
        "oib": tenant.oib,
        "telefon": tenant.telefon,
        "web": tenant.web,
    }


def _patient_dict(patient: Patient) -> dict:
    return {
        "ime": patient.ime,
        "prezime": patient.prezime,
        "oib": patient.oib,
        "adresa": patient.adresa,
        "grad": patient.grad,
        "postanski_broj": patient.postanski_broj,
    }


def _to_ascii(s: str) -> str:
    cro_to_ascii = {
        "š": "s",
        "Š": "S",
        "đ": "dj",
        "Đ": "Dj",
        "č": "c",
        "Č": "C",
        "ć": "c",
        "Ć": "C",
        "ž": "z",
        "Ž": "Z",
    }
    for cro, ascii_ch in cro_to_ascii.items():
        s = s.replace(cro, ascii_ch)
    return s


def _generate_pdf(tenant: Tenant, patient: Patient, predracun_dict: dict) -> bytes:
    generator = PredracunPDFGenerator(
        tenant=_tenant_dict(tenant),
        patient=_patient_dict(patient),
        predracun=predracun_dict,
        stavke=predracun_dict.get("stavke", []),
    )
    return generator.generate()


def _pdf_response(pdf_bytes: bytes, predracun_dict: dict, patient: Patient) -> StreamingResponse:
    broj = predracun_dict["broj"]
    ime = _to_ascii(patient.ime or "")
    prezime = _to_ascii(patient.prezime or "")
    filename = f"predracun_{broj}_{ime}_{prezime}.pdf"
    encoded = quote(filename.encode("utf-8"))

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{encoded}",
        },
    )


@router.post("/predracuni", status_code=status.HTTP_201_CREATED)
async def create_predracun(
    data: PredracunCreate,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    """Create a predračun from selected performed procedures and return the PDF."""
    result = await predracun_service.create_predracun(
        db,
        tenant_id=current_user.tenant_id,
        patient_id=data.patient_id,
        performed_procedure_ids=data.performed_procedure_ids,
        napomena=data.napomena,
        created_by=current_user.id,
    )

    tenant = await db.get(Tenant, current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ustanova nije pronađena")

    patient = await db.get(Patient, data.patient_id)
    if not patient or patient.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")

    pdf_bytes = _generate_pdf(tenant, patient, result)
    return _pdf_response(pdf_bytes, result, patient)


@router.get("/predracuni", response_model=PaginatedResponse[PredracunRead])
async def list_predracuni(
    patient_id: uuid.UUID = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List predračuni for a patient."""
    items, total = await predracun_service.list_predracuni(
        db,
        current_user.tenant_id,
        patient_id,
        skip,
        limit,
    )
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/predracuni/{predracun_id}/pdf")
async def download_predracun_pdf(
    predracun_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-download a previously generated predračun as PDF."""
    result = await predracun_service.get_predracun(db, current_user.tenant_id, predracun_id)

    tenant = await db.get(Tenant, current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ustanova nije pronađena")

    patient = await db.get(Patient, result["patient_id"])
    if not patient or patient.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacijent nije pronađen")

    pdf_bytes = _generate_pdf(tenant, patient, result)
    return _pdf_response(pdf_bytes, result, patient)
