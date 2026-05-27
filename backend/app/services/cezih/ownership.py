"""Ownership classification: is a CEZIH record ours (this tenant) or external?

CEZIH read responses carry the issuing identity:
- Encounters (visits): ``serviceProvider`` Organization — HZZO šifra ustanove.
- DocumentReferences (nalazi): ``author``/``custodian`` Organization (HZZO šifra) and
  ``author`` Practitioner (HZJZ broj).
- Conditions (cases): ``recorder``/``asserter`` Practitioner (HZJZ broj) — no organization.

A record is "ours" when its organisation šifra matches the tenant's ``sifra_ustanove`` OR any
of its practitioner HZJZ ids matches one of the tenant's doctors. This identity signal is
authoritative regardless of whether a local mirror row survived (mirror rows are lost across
test-env DB resets and ids don't always line up, which previously mislabelled our own records
as external). Mirrors how visits already classify Naša/Ostalo by ``service_provider_code``.

See ``docs/CEZIH/findings/2026-05-27-cezih-read-identity-fields-ownership.md``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class TenantCezihIdentity:
    """The current tenant's CEZIH identifiers used to classify record ownership."""

    sifra_ustanove: str | None
    practitioner_ids: frozenset[str]

    def owns(
        self,
        *,
        org_codes: Iterable[str | None] = (),
        practitioner_ids: Iterable[str | None] = (),
    ) -> bool:
        """True if any org šifra matches our institution OR any HZJZ matches our doctors."""
        if self.sifra_ustanove:
            for code in org_codes:
                if code and code == self.sifra_ustanove:
                    return True
        if self.practitioner_ids:
            for pid in practitioner_ids:
                if pid and pid in self.practitioner_ids:
                    return True
        return False


async def load_tenant_cezih_identity(db: AsyncSession, tenant_id: UUID) -> TenantCezihIdentity:
    """Load the tenant's šifra ustanove + the set of its doctors' HZJZ practitioner ids."""
    from app.models.tenant import Tenant
    from app.models.user import User

    tenant = await db.get(Tenant, tenant_id)
    sifra = (getattr(tenant, "sifra_ustanove", None) or None) if tenant else None
    rows = await db.execute(
        select(User.practitioner_id).where(
            User.tenant_id == tenant_id,
            User.practitioner_id.is_not(None),
        )
    )
    practitioner_ids = frozenset(pid for (pid,) in rows.all() if pid)
    return TenantCezihIdentity(sifra_ustanove=sifra, practitioner_ids=practitioner_ids)
