"""CEZIH FHIR HTTP API calls, organised by resource domain.

This package re-exports all public symbols from domain-specific modules
to maintain backward compatibility with existing imports.
"""

from __future__ import annotations

# Re-export all domain modules
from app.services.cezih.fhir_api.condition import *  # noqa: F401,F403
from app.services.cezih.fhir_api.documents import *  # noqa: F401,F403
from app.services.cezih.fhir_api.encounter import *  # noqa: F401,F403
from app.services.cezih.fhir_api.identifiers import *  # noqa: F401,F403
from app.services.cezih.fhir_api.patient import *  # noqa: F401,F403
from app.services.cezih.fhir_api.pmir import *  # noqa: F401,F403
from app.services.cezih.fhir_api.registries import *  # noqa: F401,F403
