"""One-off seed for Poliklinika Gradiski demo data."""
import json
import urllib.request
from datetime import datetime, timedelta

BASE = "http://localhost:8000/api"

patients = [
    {
        "ime": "Ana", "prezime": "Bilic", "datum_rodjenja": "1985-03-12", "spol": "Z",
        "oib": "10000000018", "mbo": "987654325", "adresa": "Ilica 45", "grad": "Zagreb",
        "postanski_broj": "10000", "telefon": "01/234-5678", "mobitel": "091/123-4567",
        "email": "ana.bilic@email.hr",
    },
    {
        "ime": "Marko", "prezime": "Vidovic", "datum_rodjenja": "1972-07-25", "spol": "M",
        "oib": "11111111127", "mbo": "876543215", "adresa": "Savska 18", "grad": "Zagreb",
        "postanski_broj": "10000", "telefon": "01/345-6789", "mobitel": "092/234-5678",
        "email": "marko.vidovic@email.hr",
    },
    {
        "ime": "Lucija", "prezime": "Radic", "datum_rodjenja": "1990-11-08", "spol": "Z",
        "oib": "12222222237", "mbo": "765432115", "adresa": "Vukovarska 67", "grad": "Zagreb",
        "postanski_broj": "10000", "telefon": "01/456-7890", "mobitel": "098/345-6789",
        "email": "lucija.radic@email.hr",
    },
    {
        "ime": "Ante", "prezime": "Knezevic", "datum_rodjenja": "1968-01-30", "spol": "M",
        "oib": "13333333347", "mbo": "654321095", "adresa": "Frankopanska 22", "grad": "Zagreb",
        "postanski_broj": "10000", "telefon": "01/567-8901", "mobitel": "099/456-7890",
        "email": "ante.knezevic@email.hr",
    },
    {
        "ime": "Maja", "prezime": "Tomic", "datum_rodjenja": "1995-06-14", "spol": "Z",
        "oib": "14444444450", "mbo": "543210985", "adresa": "Maksimirska 33", "grad": "Zagreb",
        "postanski_broj": "10000", "telefon": "01/678-9012", "mobitel": "091/567-8901",
        "email": "maja.tomic@email.hr",
    },
    {
        "ime": "Ivan", "prezime": "Horvat", "datum_rodjenja": "1980-09-22", "spol": "M",
        "oib": "15555555569", "mbo": "432109875", "adresa": "Heinzelova 15", "grad": "Zagreb",
        "postanski_broj": "10000", "telefon": "01/789-0123", "mobitel": "092/678-9012",
        "email": "ivan.horvat2@email.hr",
    },
    {
        "ime": "Petra", "prezime": "Bozic", "datum_rodjenja": "1988-04-05", "spol": "Z",
        "oib": "16666666674", "mbo": "321098765", "adresa": "Tkalciceva 9", "grad": "Zagreb",
        "postanski_broj": "10000", "telefon": "01/890-1234", "mobitel": "098/789-0123",
        "email": "petra.bozic@email.hr",
    },
    {
        "ime": "Dario", "prezime": "Simic", "datum_rodjenja": "1975-12-18", "spol": "M",
        "oib": "17777777787", "mbo": "210987655", "adresa": "Branimirova 38", "grad": "Zagreb",
        "postanski_broj": "10000", "telefon": "01/901-2345", "mobitel": "099/890-1234",
        "email": "dario.simic@email.hr",
    },
    {
        "ime": "Sara", "prezime": "Ljubic", "datum_rodjenja": "1998-02-28", "spol": "Z",
        "oib": "18888888897", "mbo": "109876545", "adresa": "Palmoticeva 4", "grad": "Zagreb",
        "postanski_broj": "10000", "telefon": "01/012-3456", "mobitel": "091/901-2345",
        "email": "sara.ljubic@email.hr",
    },
    {
        "ime": "Nikola", "prezime": "Peric", "datum_rodjenja": "1963-08-11", "spol": "M",
        "oib": "20000000009", "mbo": "098765435", "adresa": "Kaptolska 7", "grad": "Zagreb",
        "postanski_broj": "10000", "telefon": "01/123-9876", "mobitel": "092/012-3456",
        "email": "nikola.peric@email.hr",
    },
]


def api(method, path, data=None, token=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(BASE + path, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        return json.loads(urllib.request.urlopen(req).read())
    except Exception as e:
        err = e.read().decode() if hasattr(e, "read") else str(e)
        return {"error": err}


def main():
    # Login
    login = api("POST", "/auth/login", {"email": "ivan.gradiski@gradiski.hr", "password": "Demo1234!"})
    token = login["access_token"]
    doctor_id = login["user"]["id"]
    print(f"Logged in: {login['user']['ime']} {login['user']['prezime']}")

    # Create patients (skip if already exists)
    patient_ids = []
    for p in patients:
        r = api("POST", "/patients", p, token)
        if "id" in r:
            patient_ids.append(r["id"])
        elif "vec postoji" in str(r.get("error", "")):
            # Fetch existing patients
            pass
        else:
            print(f"  ERR {p['ime']}: {r}")

    # If no new patients, fetch existing
    if not patient_ids:
        existing = api("GET", "/patients?limit=20", None, token)
        if isinstance(existing, list):
            patient_ids = [p["id"] for p in existing]
        elif isinstance(existing, dict) and "items" in existing:
            patient_ids = [p["id"] for p in existing["items"]]
        print(f"Using {len(patient_ids)} existing patients")
    else:
        print(f"Patients: {len(patient_ids)}/{len(patients)}")

    # Appointments
    appt_types = ["pregled", "kontrola", "lijecenje", "hitno", "konzultacija"]
    hours = [8, 9, 10, 11, 13, 14, 15, 16, 9, 10]
    minutes = ["00", "30", "00", "30", "00", "00", "30", "00", "30", "00"]
    today = datetime.now().strftime("%Y-%m-%d")

    today_count = 0
    for i, pid in enumerate(patient_ids):
        vrsta = appt_types[i % len(appt_types)]
        dv = f"{today}T{hours[i]:02d}:{minutes[i]}:00"
        print(f"  appt {i}: vrsta={vrsta}, dv={dv}")
        data = {
            "patient_id": pid,
            "doktor_id": doctor_id,
            "datum_vrijeme": dv + "+01:00",
            "trajanje_minuta": 30,
            "vrsta": vrsta,
            "napomena": "",
        }
        r = api("POST", "/appointments", data, token)
        if "id" in r:
            today_count += 1
        else:
            print(f"  ERR appt today {i}: {r}")
    print(f"Appointments today: {today_count}")

    # This week
    week_count = 0
    for day_offset in range(1, 5):
        d = (datetime.now() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        for j in range(3):
            idx = (day_offset * 3 + j) % len(patient_ids)
            h = 8 + j * 2
            data = {
                "patient_id": patient_ids[idx],
                "doktor_id": doctor_id,
                "datum_vrijeme": f"{d}T{h:02d}:00:00+01:00",
                "trajanje_minuta": 30,
                "vrsta": appt_types[(day_offset + j) % len(appt_types)],
                "napomena": "",
            }
            r = api("POST", "/appointments", data, token)
            if "id" in r:
                week_count += 1
    print(f"Appointments rest of week: {week_count}")

    # Create medical records for first few patients
    record_count = 0
    diagnoses = [
        "Akutni bronhitis",
        "Hipertenzija - redovita kontrola",
        "Lumbalni sindrom",
        "Allergijski rinitis",
        "Gastroezofagealni refluks",
    ]
    for i in range(min(5, len(patient_ids))):
        data = {
            "patient_id": patient_ids[i],
            "datum": today,
            "tip": "pregled",
            "dijagnoza_tekst": diagnoses[i],
            "sadrzaj": (
                f"Klinicki pregled pacijenta. {diagnoses[i]}. "
                f"Preporucena terapija i kontrola za 2 tjedna. "
                f"Propisana terapija prema protokolu."
            ),
        }
        r = api("POST", "/medical-records", data, token)
        if "id" in r:
            record_count += 1
        else:
            print(f"  ERR record {i}: {r}")
    print(f"Medical records: {record_count}")

    # Create procedures
    proc_count = 0
    procs = [
        {"naziv": "Pregled opce medicine", "cijena": 30.00, "sifra": "101", "kategorija": "Pregled"},
        {"naziv": "Specijalisticki pregled", "cijena": 50.00, "sifra": "102", "kategorija": "Pregled"},
        {"naziv": "Kontrolni pregled", "cijena": 20.00, "sifra": "103", "kategorija": "Pregled"},
        {"naziv": "EKG", "cijena": 15.00, "sifra": "201", "kategorija": "Dijagnostika"},
        {"naziv": "Laboratorijska analiza krvi", "cijena": 25.00, "sifra": "202", "kategorija": "Dijagnostika"},
        {"naziv": "Ultrazvuk trbuha", "cijena": 60.00, "sifra": "203", "kategorija": "Dijagnostika"},
        {"naziv": "Injekcija IM", "cijena": 10.00, "sifra": "301", "kategorija": "Intervencija"},
        {"naziv": "Previjanje", "cijena": 8.00, "sifra": "302", "kategorija": "Intervencija"},
    ]
    for proc in procs:
        r = api("POST", "/procedures", proc, token)
        if "id" in r:
            proc_count += 1
        else:
            print(f"  ERR proc: {r}")
    print(f"Procedures: {proc_count}")

    print("DONE - Poliklinika Gradiski seeded!")


if __name__ == "__main__":
    main()
