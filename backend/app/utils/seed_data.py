import uuid
from datetime import date, datetime, timedelta

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
    "admin": "admin@horvat.hr",
    "doctor": "kovacevic@horvat.hr",
    "nurse": "juric@horvat.hr",
}
DEMO_PASSWORD = "Demo1234!"

# ---------------------------------------------------------------------------
# Default procedure catalog (same as before)
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
# Demo data
# ---------------------------------------------------------------------------
_PATIENTS = [
    # (ime, prezime, datum_rodjenja, spol, oib, mbo, adresa, grad, postanski_broj, telefon, mobitel, email)
    (
        "Ivan", "Horvat", "1985-03-15", "M", "12345678901", "123456789",
        "Ulica grada Vukovara 12", "Zagreb", "10000", "01/234-5678", "091/234-5678", "ivan.horvat@email.hr",
    ),
    (
        "Ana", "Kovačević", "1990-07-22", "Z", "23456789012", "234567890",
        "Savska cesta 45", "Zagreb", "10000", "01/345-6789", "092/345-6789", "ana.kovacevic@email.hr",
    ),
    (
        "Marko", "Babić", "1978-11-08", "M", "34567890123", "345678901",
        "Trg bana Jelačića 8", "Zagreb", "10000", "01/456-7890", "098/456-7890", "marko.babic@email.hr",
    ),
    (
        "Petra", "Novak", "1995-01-30", "Z", "45678901234", "456789012",
        "Ilica 22", "Zagreb", "10000", "01/567-8901", "099/567-8901", "petra.novak@email.hr",
    ),
    (
        "Josip", "Marić", "1982-09-12", "M", "56789012345", "567890123",
        "Vukovarska 33", "Zagreb", "10000", "01/678-9012", "091/678-9012", "josip.maric@email.hr",
    ),
    (
        "Ivana", "Jurić", "1988-05-17", "Z", "67890123456", "678901234",
        "Maksimirska 67", "Zagreb", "10000", "01/789-0123", "092/789-0123", "ivana.juric@email.hr",
    ),
    (
        "Tomislav", "Knežević", "1972-12-03", "M", "78901234567", "789012345",
        "Heinzelova 15", "Zagreb", "10000", "01/890-1234", "098/890-1234", "tomislav.knezevic@email.hr",
    ),
    (
        "Maja", "Vidović", "1993-04-25", "Z", "89012345678", "890123456",
        "Palmotićeva 9", "Zagreb", "10000", "01/901-2345", "099/901-2345", "maja.vidovic@email.hr",
    ),
    (
        "Ante", "Perić", "1980-08-19", "M", "90123456789", "901234567",
        "Kaptolska 4", "Zagreb", "10000", "01/012-3456", "091/012-3456", "ante.peric@email.hr",
    ),
    (
        "Lucija", "Matić", "1997-06-11", "Z", "01234567890", "012345678",
        "Gundulićeva 28", "Zagreb", "10000", "01/123-4567", "092/123-4567", "lucija.matic@email.hr",
    ),
    (
        "Nikola", "Pavlović", "1975-02-28", "M", "11223344556", "112233445",
        "Frankopanska 11", "Zagreb", "10000", "01/234-9876", "098/234-9876", "nikola.pavlovic@email.hr",
    ),
    (
        "Sara", "Božić", "1999-10-14", "Z", "22334455667", "223344556",
        "Tkalčićeva 19", "Zagreb", "10000", "01/345-9876", "099/345-9876", "sara.bozic@email.hr",
    ),
    (
        "Filip", "Šimić", "1986-07-07", "M", "33445566778", "334455667",
        "Radnička 52", "Zagreb", "10000", "01/456-9876", "091/456-9876", "filip.simic@email.hr",
    ),
    (
        "Martina", "Tomić", "1991-03-22", "Z", "44556677889", "445566778",
        "Branimirova 38", "Zagreb", "10000", "01/567-9876", "092/567-9876", "martina.tomic@email.hr",
    ),
    (
        "Dario", "Vuković", "1969-11-30", "M", "55667788990", "556677889",
        "Ljubljanska 7", "Zagreb", "10000", "01/678-9876", "098/678-9876", "dario.vukovic@email.hr",
    ),
    (
        "Helena", "Radić", "1983-09-05", "Z", "66778899001", "667788990",
        "Maračićeva 16", "Zagreb", "10000", "01/789-9876", "099/789-9876", "helena.radic@email.hr",
    ),
    (
        "Luka", "Jukić", "1976-01-18", "M", "77889900112", "778899001",
        "Sveti Duh 24", "Zagreb", "10000", "01/890-9876", "091/890-9876", "luka.jukic@email.hr",
    ),
    (
        "Anja", "Stanković", "1994-05-09", "Z", "88990011223", "889900112",
        "Nova ves 41", "Zagreb", "10000", "01/901-9876", "092/901-9876", "anja.stankovic@email.hr",
    ),
    (
        "Matej", "Vučić", "1981-12-25", "M", "99001122334", "990011223",
        "Vlaška 55", "Zagreb", "10000", "01/012-9876", "098/012-9876", "matej.vucic@email.hr",
    ),
    (
        "Nina", "Grgić", "1996-08-13", "Z", "00112233445", "001122334",
        "Dernečina 63", "Zagreb", "10000", "01/123-9876", "099/123-9876", "nina.grgic@email.hr",
    ),
]


def _patient_uuid(i: int) -> uuid.UUID:
    return uuid.UUID(int=_PATIENT_BASE.int + i)


async def seed_demo_data(db: AsyncSession) -> None:
    """Create a full demo dataset. Idempotent — skips if demo tenant already exists."""

    from app.models.appointment import Appointment
    from app.models.tenant import Tenant
    from app.models.user import User

    # Check idempotency
    result = await db.execute(select(Tenant).where(Tenant.id == TENANT_UUID))
    if result.scalar_one_or_none() is not None:
        print("Demo tenant already exists — skipping seed.")
        return

    # --- Tenant ---
    tenant = Tenant(
        id=TENANT_UUID,
        naziv="Poliklinika Horvat",
        vrsta="poliklinika",
        email="info@horvat-med.hr",
        telefon="01/234-5678",
        adresa="Ulica grada Vukovara 12",
        oib="98765432109",
        grad="Zagreb",
        postanski_broj="10000",
        zupanija="Grad Zagreb",
        plan_tier="poliklinika",
        cezih_status="nepovezano",
        is_active=True,
    )
    db.add(tenant)

    # --- Users ---
    users_data = [
        (ADMIN_UUID, DEMO_EMAILS["admin"], DEMO_PASSWORD, "Ivan", "Horvat", "dr. med.", "admin"),
        (DOCTOR_UUID, DEMO_EMAILS["doctor"], DEMO_PASSWORD, "Matea", "Kovačević", "dr. med.", "doctor"),
        (NURSE_UUID, DEMO_EMAILS["nurse"], DEMO_PASSWORD, "Sanja", "Jurić", None, "nurse"),
    ]
    users = []
    for uid, email, pwd, ime, prezime, titula, role in users_data:
        u = User(
            id=uid,
            tenant_id=TENANT_UUID,
            email=email,
            hashed_password=hash_password(pwd),
            ime=ime,
            prezime=prezime,
            titula=titula,
            role=role,
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

    # --- Patients ---
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

    # --- Appointments (spread across current week) ---
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    appt_specs = [
        # (patient_idx, doctor_idx, day_offset, hour, minute, duration, status, vrsta)
        (0, 1, 0, 8, 0, 30, "zavrsen", "pregled"),
        (1, 1, 0, 9, 0, 45, "zavrsen", "lijecenje"),
        (2, 1, 0, 10, 0, 30, "potvrdjen", "pregled"),
        (3, 1, 1, 8, 30, 30, "zavrsen", "kontrola"),
        (4, 1, 1, 10, 0, 60, "zavrsen", "lijecenje"),
        (5, 1, 1, 14, 0, 30, "otkazan", "higijena"),
        (6, 1, 2, 9, 0, 30, "zavrsen", "pregled"),
        (7, 1, 2, 11, 0, 45, "zavrsen", "lijecenje"),
        (8, 1, 2, 14, 30, 30, "zakazan", "kontrola"),
        (9, 1, 3, 8, 0, 30, "zakazan", "pregled"),
        (10, 1, 3, 9, 30, 60, "zakazan", "lijecenje"),
        (11, 1, 3, 11, 0, 30, "potvrdjen", "higijena"),
        (12, 1, 4, 8, 0, 30, "zakazan", "pregled"),
        (13, 1, 4, 9, 0, 45, "zakazan", "kontrola"),
        (14, 1, 4, 10, 30, 30, "zakazan", "pregled"),
        (15, 1, 4, 13, 0, 30, "otkazan", "higijena"),
        (0, 1, 5, 9, 0, 30, "zakazan", "kontrola"),
        (3, 1, 5, 10, 30, 45, "zakazan", "lijecenje"),
        (6, 1, 6, 10, 0, 30, "zakazan", "pregled"),
        (9, 1, 6, 11, 0, 30, "zakazan", "higijena"),
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

    # --- Medical records (for finished appointments) ---
    records_data = [
        # (patient_idx, appt_idx, tip, mkb, dijagnoza_tekst, sadrzaj)
        (
            0, 0, "Pregled", "J06.9", "Akutna infekcija gornjih dišnih putova",
            "Pacijent se javlja zbog kašlja i povišene temperature 3 dana. "
            "Faringijski zid hiperemičan. Preporučena terapija i mirovanje.",
        ),
        (
            1, 1, "Liječenje", "M54.5", "Bol u donjem dijelu leđa",
            "Akutni lumbalni sindrom. Propisana NSAID terapija, "
            "kineziterapija za 5 dana. Savjetovana promjena načina rada.",
        ),
        (
            3, 3, "Kontrola", "I10", "Arterijska hipertenzija",
            "Kontrola tlaka nakon uvođenja terapije. Tlak 135/85 mmHg, "
            "zadovoljavajuća regulacija. Nastaviti trenutnu terapiju.",
        ),
        (
            4, 4, "Liječenje", "S93.4", "Uganuće skočnog zgloba",
            "Akutno uganuće lijevog skočnog zgloba. "
            "Imobilizacija, hlađenje, elevacija. Kontrola za 7 dana.",
        ),
        (
            6, 6, "Pregled", "E11.9", "Dijabetes tip 2",
            "Redovna kontrola. HbA1c 6.8%, glikemija natašte 7.2 mmol/L. "
            "Terapija se nastavlja, preporučena dijetetska regulacija.",
        ),
        (
            7, 7, "Liječenje", "J20.9", "Akutni bronhitis",
            "Produktivni kašalj 5 dana. Auskultacija: obostrano oslabljen "
            "šum, piskovi. Propisana mukolitička terapija.",
        ),
        (
            10, 9, "Pregled", "K30", "Funkcionalna dispepsija",
            "Pacijent se žali na epigastrične tegobe nakon jela. "
            "Nalaz UZ abdomena uredan. Preporučena dijeta i prokinetik.",
        ),
        (
            11, 10, "Pregled", "M79.1", "Mialgija",
            "Bol u muskulaturi ramenog obruča obostrano. "
            "Ograničena abdukcija. Preporučena fizikalna terapija 10 tretmana.",
        ),
        (
            12, 11, "Kontrola", "J06.9",
            "Akutna infekcija gornjih dišnih putova",
            "Kontrola nakon terapije. Simptomi u povlačenju, afebrilan. "
            "Nalazi uredni. Završetak terapije.",
        ),
        (
            13, 12, "Pregled", "L30.9", "Dermatitis",
            "Eritematozne promjene na podlakticama. "
            "Topikalna kortikosteroidna terapija. "
            "Savjetovano izbjegavanje iritanasa.",
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
        (0, "D001", 0, None, "Opći pregled"),
        (1, "P002", 1, "Lumbalna kralježnica", "Specijalistički pregled kralježnice"),
        (3, "P003", 3, None, "Kontrola tlaka"),
        (4, "K001", 4, "Lijevi skočni zglob", "Imobilizacija uganuća"),
        (6, "P002", 6, None, "Kontrola dijabetesa"),
        (6, "L001", 6, None, "Krvna slika"),
        (7, "T001", 7, None, "IM injekcija"),
        (10, "P002", 9, None, "Gastroenterološki pregled"),
        (11, "R002", 10, "Rameni obruč", "Fizikalna terapija"),
        (12, "P003", 11, None, "Kontrola nakon infekcije"),
        (13, "D001", 12, None, "Dermatološki pregled"),
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
    print("Demo data seeded successfully.")
    print("  Tenant: Poliklinika Horvat (plan: poliklinika)")
    print(f"  Admin:  {DEMO_EMAILS['admin']} / {DEMO_PASSWORD}")
    print(f"  Doctor: {DEMO_EMAILS['doctor']} / {DEMO_PASSWORD}")
    print(f"  Nurse:  {DEMO_EMAILS['nurse']} / {DEMO_PASSWORD}")
    print(f"  Patients: {len(_PATIENTS)}")
    print(f"  Appointments: {len(appt_specs)}")
    print(f"  Medical records: {len(records_data)}")
    print(f"  Performed procedures: {len(performed_data)}")
