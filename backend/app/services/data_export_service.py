"""GDPR Art. 15/20 — Patient data export service.

Aggregates all patient-related data across 13 tables into a structured
dict ready for JSON serialization or ZIP bundling.
"""

import json
import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.audit_log import AuditLog
from app.models.cezih_case import CezihCase
from app.models.document import Document
from app.models.medical_record import MedicalRecord
from app.models.patient import Patient
from app.models.predracun import Predracun, PredracunStavka
from app.models.prescription import Prescription
from app.models.procedure import PerformedProcedure, Procedure
from app.models.tenant import Tenant
from app.models.user import User


def _fmt(value: object) -> object:
    """Make a value JSON-safe (UUID → str, datetime → ISO 8601)."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _model_to_dict(obj: object) -> dict:
    """Convert a SQLAlchemy model instance to a plain dict, skipping internals."""
    exclude = {"hashed_password", "agent_secret"}
    return {
        c.key: _fmt(getattr(obj, c.key))
        for c in obj.__table__.columns  # type: ignore[union-attr, attr-defined]
        if c.key not in exclude
    }


async def _load_doctor_names(db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, str]:
    """Return {user_id_str: 'Ime Prezime'} for all doctors in the tenant."""
    result = await db.execute(select(User.id, User.ime, User.prezime).where(User.tenant_id == tenant_id))
    return {str(row.id): f"{row.ime} {row.prezime}" for row in result.all()}


async def export_patient_data(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
) -> dict:
    """Aggregate all patient data into a structured dict for JSON export."""

    # --- Verify patient belongs to tenant ---
    patient = await db.get(Patient, patient_id)
    if not patient or patient.tenant_id != tenant_id:
        return {}

    tenant = await db.get(Tenant, tenant_id)
    tenant_name = tenant.naziv if tenant else "Nepoznato"

    doctor_names = await _load_doctor_names(db, tenant_id)

    # --- Personal data ---
    patient_data = _model_to_dict(patient)

    # --- Medical records ---
    mr_result = await db.execute(
        select(MedicalRecord)
        .where(MedicalRecord.tenant_id == tenant_id, MedicalRecord.patient_id == patient_id)
        .order_by(MedicalRecord.datum.desc())
    )
    medical_records = []
    for mr in mr_result.scalars().all():
        rec = _model_to_dict(mr)
        rec["_doktor"] = doctor_names.get(str(mr.doktor_id), "")
        medical_records.append(rec)

    # --- Prescriptions ---
    pr_result = await db.execute(
        select(Prescription)
        .where(Prescription.tenant_id == tenant_id, Prescription.patient_id == patient_id)
        .order_by(Prescription.created_at.desc())
    )
    prescriptions = []
    for pr in pr_result.scalars().all():
        rec = _model_to_dict(pr)
        # lijekovi is JSONB — already a list
        if isinstance(pr.lijekovi, str):
            rec["lijekovi"] = json.loads(pr.lijekovi)
        rec["_doktor"] = doctor_names.get(str(pr.doktor_id), "")
        prescriptions.append(rec)

    # --- Performed procedures ---
    pp_result = await db.execute(
        select(PerformedProcedure)
        .where(PerformedProcedure.tenant_id == tenant_id, PerformedProcedure.patient_id == patient_id)
        .order_by(PerformedProcedure.datum.desc())
    )
    pp_rows = pp_result.scalars().all()

    procedure_ids = list({pp.procedure_id for pp in pp_rows})
    if procedure_ids:
        proc_result = await db.execute(select(Procedure).where(Procedure.id.in_(procedure_ids)))
        proc_map = {p.id: p for p in proc_result.scalars().all()}
    else:
        proc_map = {}

    performed_procedures = []
    for pp in pp_rows:
        rec = _model_to_dict(pp)
        proc = proc_map.get(pp.procedure_id)
        rec["_naziv_postupka"] = proc.naziv if proc else ""
        rec["_sifra_postupka"] = proc.sifra if proc else ""
        rec["_doktor"] = doctor_names.get(str(pp.doktor_id), "")
        performed_procedures.append(rec)

    # --- Appointments ---
    ap_result = await db.execute(
        select(Appointment)
        .where(Appointment.tenant_id == tenant_id, Appointment.patient_id == patient_id)
        .order_by(Appointment.datum_vrijeme.desc())
    )
    appointments = []
    for ap in ap_result.scalars().all():
        rec = _model_to_dict(ap)
        rec["_doktor"] = doctor_names.get(str(ap.doktor_id), "")
        appointments.append(rec)

    # --- Documents (metadata only — files handled separately for ZIP) ---
    doc_result = await db.execute(
        select(Document)
        .where(Document.tenant_id == tenant_id, Document.patient_id == patient_id)
        .order_by(Document.created_at.desc())
    )
    documents = [_model_to_dict(d) for d in doc_result.scalars().all()]

    # --- Invoices (predracuni + stavke) ---
    inv_result = await db.execute(
        select(Predracun)
        .where(Predracun.tenant_id == tenant_id, Predracun.patient_id == patient_id)
        .order_by(Predracun.datum.desc())
    )
    inv_rows = inv_result.scalars().all()

    predracun_ids = [inv.id for inv in inv_rows]
    if predracun_ids:
        all_stavke_result = await db.execute(
            select(PredracunStavka).where(PredracunStavka.predracun_id.in_(predracun_ids))
        )
        stavke_by_predracun: dict[uuid.UUID, list] = {}
        for s in all_stavke_result.scalars().all():
            stavke_by_predracun.setdefault(s.predracun_id, []).append(_model_to_dict(s))
    else:
        stavke_by_predracun = {}

    invoices = []
    for inv in inv_rows:
        inv_data = _model_to_dict(inv)
        inv_data["stavke"] = stavke_by_predracun.get(inv.id, [])
        invoices.append(inv_data)

    # --- CEZIH cases ---
    cc_result = await db.execute(
        select(CezihCase)
        .where(CezihCase.tenant_id == tenant_id, CezihCase.patient_id == patient_id)
        .order_by(CezihCase.created_at.desc())
    )
    cezih_cases = [_model_to_dict(c) for c in cc_result.scalars().all()]

    # --- Audit log for this patient ---
    audit_result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.resource_type == "patient",
            AuditLog.resource_id == patient_id,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(500)
    )
    access_log = []
    for entry in audit_result.scalars().all():
        rec = _model_to_dict(entry)
        rec["_user_name"] = doctor_names.get(str(entry.user_id), "")
        access_log.append(rec)

    return {
        "export_metadata": {
            "format_version": "1.0",
            "exported_at": datetime.now(UTC).isoformat(),
            "data_controller": tenant_name,
            "purpose": "GDPR Art. 15/20 — Pravo na pristup / Prenosivost podataka",
        },
        "patient": patient_data,
        "medical_records": medical_records,
        "prescriptions": prescriptions,
        "performed_procedures": performed_procedures,
        "appointments": appointments,
        "documents": documents,
        "invoices": invoices,
        "cezih_cases": cezih_cases,
        "access_log": access_log,
    }


def build_zip(data: dict, tenant_id: uuid.UUID) -> BytesIO:
    """Build a ZIP archive containing data.json + all uploaded documents."""
    import zipfile

    json_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("podaci.json", json_bytes)

        # Attach uploaded documents if they exist on disk
        for doc_meta in data.get("documents", []):
            file_path = doc_meta.get("file_path")
            if not file_path:
                continue
            p = Path(file_path)
            if not p.exists():
                p = Path("uploads") / str(tenant_id) / p.name
            if p.exists():
                zf.write(p, arcname=f"dokumenti/{p.name}")

    buf.seek(0)
    return buf
