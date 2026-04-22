"""GDPR Art. 15/20 — Patient data export endpoints.

GET /patient-rights/{patient_id}/export          → JSON download
GET /patient-rights/{patient_id}/export?zip=1     → ZIP (JSON + files)
"""

import json
import uuid
from io import BytesIO

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_roles
from app.models.user import User
from app.services.audit_service import write_audit
from app.services.data_export_service import build_zip, export_patient_data

router = APIRouter(prefix="/patient-rights", tags=["patient-rights"])


def _safe_filename(name: str, ext: str) -> str:
    """ASCII-safe filename, fallback to generic name."""
    try:
        ascii_name = name.encode("ascii").decode()
    except UnicodeEncodeError:
        ascii_name = "pacijent"
    return f"{ascii_name}_podaci.{ext}"


@router.get("/{patient_id}/export")
async def export_data(
    patient_id: uuid.UUID,
    zip: bool = Query(False, alias="zip"),
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user.tenant_id

    data = await export_patient_data(db, tenant_id, patient_id)
    if not data:
        return Response(status_code=404, content="Pacijent nije pronađen")

    patient_info = data.get("patient", {})
    patient_name = f"{patient_info.get('ime', 'pacijent')}_{patient_info.get('prezime', '')}"

    if zip:
        buf = build_zip(data, tenant_id)
        filename = _safe_filename(patient_name, "zip")

        await write_audit(
            db,
            tenant_id,
            current_user.id,
            action="data_export",
            resource_type="patient",
            resource_id=patient_id,
            details={"format": "zip", "include_files": True},
        )
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
        )

    # JSON export
    filename = _safe_filename(patient_name, "json")

    await write_audit(
        db,
        tenant_id,
        current_user.id,
        action="data_export",
        resource_type="patient",
        resource_id=patient_id,
        details={"format": "json"},
    )

    json_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    return StreamingResponse(
        BytesIO(json_bytes),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
