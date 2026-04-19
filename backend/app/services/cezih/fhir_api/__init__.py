"""CEZIH FHIR HTTP API calls, organised by resource domain."""
from __future__ import annotations

# Re-export from identifiers + patient + documents modules — other modules added in subsequent tasks
from app.services.cezih.fhir_api.documents import *     # noqa: F401,F403
from app.services.cezih.fhir_api.identifiers import *   # noqa: F401,F403
from app.services.cezih.fhir_api.patient import *       # noqa: F401,F403
