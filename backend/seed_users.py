"""Seed only user accounts (no demo data). Run: python seed_users.py"""
import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.tenant import Tenant
from app.models.user import User
from app.utils.security import hash_password

TENANT_UUID = uuid.UUID("11111111-1111-1111-1111-111111111111")
DEMO_PASSWORD = "Demo1234!"

USERS = [
    ("admin@horvat.hr", "Admin", "Horvat", None, "admin", None),
    ("kovacevic@horvat.hr", "Marko", "Kovačević", "dr. med.", "doctor", "7659059"),
    ("juric@horvat.hr", "Ana", "Jurić", None, "nurse", None),
    ("peric@horvat.hr", "Ivana", "Perić", None, "receptionist", None),
]


async def main() -> None:
    import os
    db_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/medical_mvp")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Create tenant if not exists
        result = await db.execute(select(Tenant).where(Tenant.id == TENANT_UUID))
        if result.scalar_one_or_none() is None:
            tenant = Tenant(
                id=TENANT_UUID,
                naziv="Ordinacija Horvat",
                vrsta="ordinacija",
                email="info@horvat.hr",
                telefon="01/234-5678",
                adresa="Zagreb",
                oib="12345678901",
                grad="Zagreb",
                postanski_broj="10000",
                zupanija="Grad Zagreb",
                plan_tier="poliklinika",
                is_active=True,
            )
            db.add(tenant)
            print(f"Created tenant: {tenant.naziv}")

        for email, ime, prezime, titula, role, pract_id in USERS:
            result = await db.execute(select(User).where(User.email == email))
            if result.scalar_one_or_none() is not None:
                print(f"  Skipping {email} (exists)")
                continue
            u = User(
                tenant_id=TENANT_UUID,
                email=email,
                hashed_password=hash_password(DEMO_PASSWORD),
                ime=ime,
                prezime=prezime,
                titula=titula,
                role=role,
                practitioner_id=pract_id,
                is_active=True,
            )
            db.add(u)
            print(f"  Created {role}: {email}")

        await db.commit()
        print("Done.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
