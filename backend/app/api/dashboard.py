from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.dashboard import DashboardStats, TodayAppointment

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _monday_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _sunday_of_week(d: date) -> date:
    return d + timedelta(days=(6 - d.weekday()))


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tid = current_user.tenant_id
    today = date.today()
    monday = _monday_of_week(today)
    sunday = _sunday_of_week(today)
    first_of_month = today.replace(day=1)

    # Today's non-cancelled appointments
    day_start = datetime.combine(today, time.min)
    day_end = datetime.combine(today, time(23, 59, 59, 999999))
    q = select(func.count()).select_from(Appointment).where(
        Appointment.tenant_id == tid,
        Appointment.datum_vrijeme >= day_start,
        Appointment.datum_vrijeme <= day_end,
        Appointment.status != "otkazan",
    )
    danas_termini = (await db.execute(q)).scalar_one()

    # Total active patients
    q = select(func.count()).select_from(Patient).where(
        Patient.tenant_id == tid,
        Patient.is_active.is_(True),
    )
    ukupno_pacijenti = (await db.execute(q)).scalar_one()

    # This week's non-cancelled appointments
    week_start = datetime.combine(monday, time.min)
    week_end = datetime.combine(sunday, time(23, 59, 59, 999999))
    q = select(func.count()).select_from(Appointment).where(
        Appointment.tenant_id == tid,
        Appointment.datum_vrijeme >= week_start,
        Appointment.datum_vrijeme <= week_end,
        Appointment.status != "otkazan",
    )
    ovaj_tjedan_termini = (await db.execute(q)).scalar_one()

    # New patients this month
    q = select(func.count()).select_from(Patient).where(
        Patient.tenant_id == tid,
        Patient.is_active.is_(True),
        Patient.created_at >= datetime.combine(first_of_month, time.min),
    )
    novi_pacijenti_mjesec = (await db.execute(q)).scalar_one()

    # CEZIH status from tenant
    tenant = await db.get(Tenant, tid)
    cezih_status = tenant.cezih_status if tenant else "nepovezano"

    return DashboardStats(
        danas_termini=danas_termini,
        ukupno_pacijenti=ukupno_pacijenti,
        ovaj_tjedan_termini=ovaj_tjedan_termini,
        novi_pacijenti_mjesec=novi_pacijenti_mjesec,
        cezih_status=cezih_status,
    )


@router.get("/today", response_model=list[TodayAppointment])
async def get_today(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tid = current_user.tenant_id
    today = date.today()
    day_start = datetime.combine(today, time.min)
    day_end = datetime.combine(today, time(23, 59, 59, 999999))

    base = (
        select(Appointment)
        .outerjoin(Patient, Appointment.patient_id == Patient.id)
        .outerjoin(User, Appointment.doktor_id == User.id)
        .where(
            Appointment.tenant_id == tid,
            Appointment.datum_vrijeme >= day_start,
            Appointment.datum_vrijeme <= day_end,
        )
        .add_columns(
            Patient.ime.label("patient_ime"),
            Patient.prezime.label("patient_prezime"),
            User.ime.label("doktor_ime"),
            User.prezime.label("doktor_prezime"),
        )
        .order_by(Appointment.datum_vrijeme)
    )

    result = await db.execute(base)
    return [
        TodayAppointment(
            id=row[0].id,
            patient_id=row[0].patient_id,
            datum_vrijeme=row[0].datum_vrijeme,
            trajanje_minuta=row[0].trajanje_minuta,
            status=row[0].status,
            vrsta=row[0].vrsta,
            patient_ime=row.patient_ime,
            patient_prezime=row.patient_prezime,
            doktor_ime=row.doktor_ime,
            doktor_prezime=row.doktor_prezime,
        )
        for row in result.all()
    ]
