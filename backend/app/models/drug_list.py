import uuid

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DrugListItem(Base):
    """Croatian drug registry — sourced from HZZO Osnovna + Dopunska lista.
    Global table, not tenant-scoped.
    """

    __tablename__ = "drug_list"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # ATC code (e.g. "J01CA04") extracted from HZZO "ATK šifra"
    atk: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # Brand name (Zaštićeni naziv), or INN if no brand
    naziv: Mapped[str] = mapped_column(String(255), nullable=False)
    # Form, strength, packaging combined (e.g. "tbl. 30x20 mg")
    oblik: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Strength extracted from oblik (e.g. "20 mg") — for backward compat
    jacina: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # Generic/INN name (Nezaštićeni naziv lijeka)
    inn: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # Marketing authorization holder
    nositelj_odobrenja: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # HZZO internal code (number after ATC code, e.g. 451)
    hzzo_sifra: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    # Which HZZO list: "OLL" (Osnovna) or "DLL" (Dopunska)
    hzzo_lista: Mapped[str] = mapped_column(String(3), nullable=False, default="")
    # Prescription type: R (na recept) or RS (bez recepta / slobodna prodaja)
    r_rs: Mapped[str] = mapped_column(String(3), nullable=False, default="")
    # Administration method: O, P, L, I
    nacin_primjene: Mapped[str] = mapped_column(String(5), nullable=False, default="")
    # Co-pay amount (from Dopunska lista)
    doplata: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    # HALMED SOAP IDs (for future HALMED integration)
    s_lij: Mapped[int | None] = mapped_column(Integer, nullable=True)
    s_lio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aktivan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    synced_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Full-text search helper: lowercase composite for ILIKE queries
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
