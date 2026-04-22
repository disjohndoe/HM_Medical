"""CEZIH dispatcher functions — re-exported by domain.

Dispatcher functions wrap FHIR API calls with:
- Audit logging (mandatory)
- Local DB synchronization (cases, visits)
- Error handling and translation
- Tenant/user context management

Import from domain modules:
  - app.services.cezih.dispatchers.common for audit helpers
  - app.services.cezih.dispatchers.patient for patient import/insurance
  - app.services.cezih.dispatchers.documents for document operations
  - app.services.cezih.dispatchers.cases for case management
  - app.services.cezih.dispatchers.visits for visit management
  - app.services.cezih.dispatchers.registries for health/terminology
"""

from __future__ import annotations

from app.services.cezih.dispatchers.cases import *  # noqa: F401,F403
from app.services.cezih.dispatchers.common import *  # noqa: F401,F403
from app.services.cezih.dispatchers.documents import *  # noqa: F401,F403
from app.services.cezih.dispatchers.patient import *  # noqa: F401,F403
from app.services.cezih.dispatchers.registries import *  # noqa: F401,F403
from app.services.cezih.dispatchers.visits import *  # noqa: F401,F403
