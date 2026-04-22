import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medical_record import MedicalRecord
from app.models.procedure import PerformedProcedure, Procedure
from app.utils.security import hash_password

# ---------------------------------------------------------------------------
# Deterministic demo UUIDs (so login credentials are predictable)
# ---------------------------------------------------------------------------
TENANT_UUID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ADMIN_UUID = uuid.UUID("22222222-2222-2222-2222-222222222222")
DOCTOR_UUID = uuid.UUID("33333333-3333-3333-3333-333333333333")
NURSE_UUID = uuid.UUID("44444444-4444-4444-4444-444444444444")

_PATIENT_BASE = uuid.UUID("a0000000-0000-0000-0000-000000000000")

DEMO_EMAILS = {
    "admin": "admin@hmdigital.hr",
    "doctor": "testni55@hmdigital.hr",
    "nurse": "sestra@hmdigital.hr",
}
DEMO_PASSWORD = "Demo1234!"

# ---------------------------------------------------------------------------
# Default procedure catalog
# ---------------------------------------------------------------------------
DEFAULT_PROCEDURES = [
    # Dijagnostika
    ("D001", "Opći pregled", "Opći medicinski pregled", 1500, 15, "dijagnostika"),
    ("D002", "Laboratorijske pretrage", "Kompletne laboratorijske pretrage krvi i urina", 3000, 10, "dijagnostika"),
    ("D003", "Ultrazvuk", "Ultrazvučni pregled", 2500, 20, "dijagnostika"),
    ("D004", "EKG", "Elektrokardiogram", 1500, 15, "dijagnostika"),
    ("D005", "RTG snimka", "Rendgenska snimka", 2000, 10, "dijagnostika"),
    # Pregled
    ("P001", "Sistematski pregled", "Kompletan sistematski pregled", 5000, 45, "pregled"),
    ("P002", "Specijalistički pregled", "Pregled specijalista", 3000, 30, "pregled"),
    ("P003", "Kontrolni pregled", "Kontrola nakon terapije", 1000, 15, "pregled"),
    # Kirurgija
    ("K001", "Manja kirurška intervencija", "Manja kirurška procedura", 5000, 30, "kirurgija"),
    ("K002", "Šivanje rane", "Zbrinjavanje i šivanje rane", 3000, 30, "kirurgija"),
    ("K003", "Uklanjanje kožnih promjena", "Ekscizija kožnih promjena", 4000, 30, "kirurgija"),
    ("K004", "Injekcija u zglobove", "Intraartikularna injekcija", 2500, 15, "kirurgija"),
    # Terapija
    ("T001", "Injekcija IM", "Intramuskularna injekcija", 500, 15, "terapija"),
    ("T002", "Injekcija IV", "Intravenska injekcija", 800, 20, "terapija"),
    ("T003", "Infuzijska terapija", "Intravenska infuzija", 2000, 60, "terapija"),
    ("T004", "Recept", "Izdavanje recepta", 300, 10, "terapija"),
    # Prevencija
    ("V001", "Cijepljenje", "Imunizacija", 1500, 15, "prevencija"),
    ("V002", "Savjetovanje", "Medicinsko savjetovanje", 1000, 30, "prevencija"),
    ("V003", "Prevencijski pregled", "Preventivni zdravstveni pregled", 2000, 30, "prevencija"),
    # Rehabilitacija
    ("R001", "Kineziterapija", "Terapija vježbama", 2000, 45, "rehabilitacija"),
    ("R002", "Fizikalna terapija", "Fizikalna medicina i rehabilitacija", 2500, 45, "rehabilitacija"),
    # Laboratorij
    ("L001", "Krvna slika", "Kompletna krvna slika", 800, 10, "laboratorij"),
    ("L002", "Biokemija", "Biokemijske pretrage", 1500, 10, "laboratorij"),
    ("L003", "Urinaliza", "Laboratorijska pretraga urina", 500, 10, "laboratorij"),
    # Ostalo
    ("O001", "Hitna pomoć", "Hitno zbrinjavanje", 3000, 30, "ostalo"),
    ("O002", "Konzultacija", "Liječnička konzultacija", 1500, 20, "ostalo"),
]


async def seed_default_procedures(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    for sifra, naziv, opis, cijena, trajanje, kategorija in DEFAULT_PROCEDURES:
        procedure = Procedure(
            tenant_id=tenant_id,
            sifra=sifra,
            naziv=naziv,
            opis=opis,
            cijena_cents=cijena,
            trajanje_minuta=trajanje,
            kategorija=kategorija,
        )
        db.add(procedure)
    await db.flush()


# ---------------------------------------------------------------------------
# HZZO certification test data (provisioned 2026-04-07)
# ---------------------------------------------------------------------------
_PATIENTS: list[tuple[Any, ...]] = [
    # (ime, prezime, datum_rodjenja, spol, oib, mbo, adresa, grad, postanski_broj, telefon, mobitel, email)
    (
        "GORAN",
        "PACPRIVATNICI19",
        "1980-01-01",
        "M",
        "99999900187",
        "999990260",
        "Testna ulica 1",
        "Zagreb",
        "10000",
        None,
        None,
        None,
    ),
]


def _patient_uuid(i: int) -> uuid.UUID:
    return uuid.UUID(int=_PATIENT_BASE.int + i)


async def seed_demo_data(db: AsyncSession) -> None:
    """Create HZZO certification test dataset. Idempotent — skips if tenant already exists."""

    from app.models.appointment import Appointment
    from app.models.tenant import Tenant
    from app.models.user import User

    # Check idempotency
    result = await db.execute(select(Tenant).where(Tenant.id == TENANT_UUID))
    if result.scalar_one_or_none() is not None:
        print("Demo tenant already exists — skipping seed.")
        return

    # --- Tenant (HZZO test institution) ---
    tenant = Tenant(
        id=TENANT_UUID,
        naziv="HM DIGITAL ordinacija",
        vrsta="ordinacija",
        email="info@hmdigital.hr",
        telefon="01/234-5678",
        adresa="Testna ulica 1",
        oib="98765432109",
        grad="Zagreb",
        postanski_broj="10000",
        zupanija="Grad Zagreb",
        plan_tier="poliklinika",
        cezih_status="testirano",
        sifra_ustanove="999001464",
        oid="1.2.162.1.999001464",
        has_hzzo_contract=True,
        is_active=True,
    )
    db.add(tenant)

    # --- Users (HZZO test doctor) ---
    users_data = [
        # (uuid, email, password, ime, prezime, titula, role, practitioner_id)
        (ADMIN_UUID, DEMO_EMAILS["admin"], DEMO_PASSWORD, "Admin", "HM Digital", None, "admin", None),
        (
            DOCTOR_UUID,
            DEMO_EMAILS["doctor"],
            DEMO_PASSWORD,
            "TESTNI55",
            "TESTNIPREZIME55",
            "dr. med.",
            "doctor",
            "7659059",
        ),
        (NURSE_UUID, DEMO_EMAILS["nurse"], DEMO_PASSWORD, "Sestra", "Test", None, "nurse", None),
    ]
    users = []
    for uid, email, pwd, ime, prezime, titula, role, pract_id in users_data:
        u = User(
            id=uid,
            tenant_id=TENANT_UUID,
            email=email,
            hashed_password=hash_password(pwd),
            ime=ime,
            prezime=prezime,
            titula=titula,
            role=role,
            practitioner_id=pract_id,
            is_active=True,
        )
        db.add(u)
        users.append(u)

    await db.flush()

    # --- Procedures (catalog) ---
    procedures_by_sifra: dict[str, Procedure] = {}
    for sifra, naziv, opis, cijena, trajanje, kategorija in DEFAULT_PROCEDURES:
        p = Procedure(
            tenant_id=TENANT_UUID,
            sifra=sifra,
            naziv=naziv,
            opis=opis,
            cijena_cents=cijena,
            trajanje_minuta=trajanje,
            kategorija=kategorija,
        )
        db.add(p)
        procedures_by_sifra[sifra] = p
    await db.flush()

    # --- Patient (HZZO test patient) ---
    patients = []
    for i, (ime, prezime, dr, spol, oib, mbo, adresa, grad, pb, tel, mob, email) in enumerate(_PATIENTS):
        from app.models.patient import Patient as PatientModel

        patient = PatientModel(
            id=_patient_uuid(i),
            tenant_id=TENANT_UUID,
            ime=ime,
            prezime=prezime,
            datum_rodjenja=date.fromisoformat(dr),
            spol=spol,
            oib=oib,
            mbo=mbo,
            adresa=adresa,
            grad=grad,
            postanski_broj=pb,
            telefon=tel,
            mobitel=mob,
            email=email,
            is_active=True,
        )
        db.add(patient)
        patients.append(patient)
    await db.flush()

    # --- Appointments (current week, all for HZZO test patient) ---
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    appt_specs = [
        # (patient_idx, doctor_idx, day_offset, hour, minute, duration, status, vrsta)
        (0, 1, 0, 8, 0, 30, "zavrsen", "pregled"),
        (0, 1, 0, 10, 0, 45, "zavrsen", "lijecenje"),
        (0, 1, 1, 9, 0, 30, "potvrdjen", "kontrola"),
        (0, 1, 2, 8, 30, 30, "zakazan", "pregled"),
        (0, 1, 3, 10, 0, 30, "zakazan", "kontrola"),
    ]
    appointments = []
    for pat_idx, doc_idx, day_off, h, m, dur, status, vrsta in appt_specs:
        appt_date = monday + timedelta(days=day_off)
        dt = datetime(appt_date.year, appt_date.month, appt_date.day, h, m)
        appt = Appointment(
            tenant_id=TENANT_UUID,
            patient_id=_patient_uuid(pat_idx),
            doktor_id=users[doc_idx].id,
            datum_vrijeme=dt,
            trajanje_minuta=dur,
            status=status,
            vrsta=vrsta,
        )
        db.add(appt)
        appointments.append(appt)
    await db.flush()

    # --- Medical records (CEZIH-eligible types for e-Nalaz testing) ---
    records_data = [
        # (patient_idx, appt_idx, tip, mkb, dijagnoza_tekst, sadrzaj)
        (
            0,
            0,
            "specijalisticki_nalaz",
            "J06.9",
            "Akutna infekcija gornjih dišnih putova",
            "Pacijent se javlja zbog kašlja i povišene temperature 3 dana. "
            "Faringijski zid hiperemičan. Preporučena terapija i mirovanje.",
        ),
        (
            0,
            1,
            "nalaz",
            "M54.5",
            "Bol u donjem dijelu leđa",
            "Akutni lumbalni sindrom. Propisana NSAID terapija, "
            "kineziterapija za 5 dana. Savjetovana promjena načina rada.",
        ),
    ]
    medical_records = []
    for pat_idx, appt_idx, tip, mkb, diag_txt, sadrzaj in records_data:
        rec = MedicalRecord(
            tenant_id=TENANT_UUID,
            patient_id=_patient_uuid(pat_idx),
            doktor_id=users[1].id,
            appointment_id=appointments[appt_idx].id,
            datum=appointments[appt_idx].datum_vrijeme.date(),
            tip=tip,
            dijagnoza_mkb=mkb,
            dijagnoza_tekst=diag_txt,
            sadrzaj=sadrzaj,
        )
        db.add(rec)
        medical_records.append(rec)
    await db.flush()

    # --- Performed procedures ---
    performed_data = [
        # (patient_idx, procedure_sifra, appt_idx, lokacija, napomena)
        (0, "P002", 0, None, "Specijalistički pregled"),
        (0, "P002", 1, "Lumbalna kralježnica", "Specijalistički pregled kralježnice"),
    ]
    for pat_idx, proc_sifra, appt_idx, lokacija, napomena in performed_data:
        proc = procedures_by_sifra[proc_sifra]
        pp = PerformedProcedure(
            tenant_id=TENANT_UUID,
            patient_id=_patient_uuid(pat_idx),
            appointment_id=appointments[appt_idx].id,
            procedure_id=proc.id,
            doktor_id=users[1].id,
            lokacija=lokacija,
            datum=appointments[appt_idx].datum_vrijeme.date(),
            cijena_cents=proc.cijena_cents,
            napomena=napomena,
        )
        db.add(pp)

    await db.commit()
    print("HZZO certification test data seeded successfully.")
    print("  Tenant: HM DIGITAL ordinacija (999001464, plan: poliklinika)")
    print(f"  Admin:  {DEMO_EMAILS['admin']} / {DEMO_PASSWORD}")
    print(f"  Doctor: {DEMO_EMAILS['doctor']} / {DEMO_PASSWORD} (HZJZ: 7659059)")
    print(f"  Nurse:  {DEMO_EMAILS['nurse']} / {DEMO_PASSWORD}")
    print("  Patient: GORAN PACPRIVATNICI19 (MBO: 999990260)")
    print(f"  Appointments: {len(appt_specs)}")
    print(f"  Medical records: {len(records_data)}")
    print(f"  Performed procedures: {len(performed_data)}")
