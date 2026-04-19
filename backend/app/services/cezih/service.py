"""CEZIH FHIR HTTP API service — re-export shim for backward compatibility.

This file re-exports all public symbols from the fhir_api/ package structure
to maintain backward compatibility with existing imports.

New code should import directly from the appropriate module:
  - app.services.cezih.fhir_api.registries for OID, terminology, subject registry
  - app.services.cezih.fhir_api.condition for case management
  - app.services.cezih.fhir_api.encounter for visit/encounter queries
  - app.services.cezih.fhir_api.pmir for foreigner registration
  - app.services.cezih.fhir_api.documents for document submission/retrieval
  - app.services.cezih.fhir_api.patient for demographics lookup
  - app.services.cezih.fhir_api.identifiers for identifier resolution
"""
from __future__ import annotations

# Re-export from new packages for back-compat during refactor
from app.services.cezih.fhir_api.condition import *  # noqa: F401,F403
from app.services.cezih.fhir_api.documents import *  # noqa: F401,F403
from app.services.cezih.fhir_api.encounter import *  # noqa: F401,F403
from app.services.cezih.fhir_api.identifiers import *  # noqa: F401,F403
from app.services.cezih.fhir_api.patient import *  # noqa: F401,F403
from app.services.cezih.fhir_api.pmir import *  # noqa: F401,F403
from app.services.cezih.fhir_api.registries import *  # noqa: F401,F403
