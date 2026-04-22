"""CEZIH dispatcher functions — re-export shim for backward compatibility.

This file re-exports all public symbols from the new dispatchers/ subpackage
to maintain backward compatibility with existing imports.

New code should import directly from the appropriate module:
  - app.services.cezih.dispatchers.common for audit helpers
  - app.services.cezih.dispatchers.patient for patient import/insurance
  - app.services.cezih.dispatchers.documents for document operations
  - app.services.cezih.dispatchers.cases for case management
  - app.services.cezih.dispatchers.visits for visit management
  - app.services.cezih.dispatchers.registries for health/terminology
"""

from __future__ import annotations

# Re-export from new dispatchers package for back-compat during refactor
from app.services.cezih.dispatchers.cases import *  # noqa: F401,F403
from app.services.cezih.dispatchers.common import *  # noqa: F401,F403
from app.services.cezih.dispatchers.documents import *  # noqa: F401,F403
from app.services.cezih.dispatchers.patient import *  # noqa: F401,F403
from app.services.cezih.dispatchers.registries import *  # noqa: F401,F403
from app.services.cezih.dispatchers.visits import *  # noqa: F401,F403
