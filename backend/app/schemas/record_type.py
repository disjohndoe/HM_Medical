from datetime import datetime
from uuid import UUID

import re

from pydantic import BaseModel, field_validator


class RecordTypeCreate(BaseModel):
    slug: str
    label: str
    color: str | None = None
    sort_order: int = 100

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]{1,48}$", v):
            raise ValueError("Slug mora biti mala slova, brojevi i podvlake (2-50 znakova), počevši slovom")
        return v

    @field_validator("label")
    @classmethod
    def validate_label(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("Naziv mora imati najmanje 2 znaka")
        return v.strip()


class RecordTypeRead(BaseModel):
    id: UUID
    tenant_id: UUID
    slug: str
    label: str
    color: str | None
    is_system: bool
    is_cezih_mandatory: bool
    is_cezih_eligible: bool
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecordTypeUpdate(BaseModel):
    label: str | None = None
    color: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None
