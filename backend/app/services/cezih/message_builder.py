# ruff: noqa: N815 — FHIR spec requires camelCase field names
"""FHIR message Bundle builder for CEZIH $process-message operations.

Builds Bundle type="message" with MessageHeader + resource + digital signature.
Used for Case Management (codes 2.x).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.services.cezih.exceptions import CezihError

logger = logging.getLogger(__name__)

# --- Constants: CEZIH FHIR identifier systems ---

MESSAGE_TYPE_SYSTEM = "http://ent.hr/fhir/CodeSystem/ehe-message-types"

# Re-export for back-compat with existing imports.
from app.services.cezih.builders.bundles import (  # noqa: F401
    build_iti65_transaction_bundle,
    build_message_bundle,
)
from app.services.cezih.builders.common import *  # noqa: F401,F403
from app.services.cezih.builders.condition import (  # noqa: F401
    CASE_ACTION_MAP,
    CASE_EVENT_PROFILE,
    build_condition_create,
    build_condition_data_update,
    build_condition_status_update,
)
from app.services.cezih.builders.encounter import (  # noqa: F401
    CS_NACIN_PRIJEMA,
    CS_TIP_POSJETE,
    CS_VRSTA_POSJETE,
    ENCOUNTER_EVENT_PROFILE_MAP,
    NACIN_PRIJEMA_MAP,
    TIP_POSJETE_MAP,
    VRSTA_POSJETE_MAP,
    VISIT_ACTION_MAP,
    build_encounter_cancel,
    build_encounter_close,
    build_encounter_create,
    build_encounter_reopen,
    build_encounter_update,
)
from app.services.cezih.response_parsing import (  # noqa: F401
    _CEZIH_DIAGNOSTIC_PATTERNS_HR,
    _CEZIH_ERROR_MESSAGES_HR,
    _translate_cezih_error,
    parse_message_response,
)
from app.services.cezih.signing import (  # noqa: F401
    SIGNATURE_TYPE_CODE,
    SIGNATURE_TYPE_SYSTEM,
    _add_signature_extsigner,
    _add_signature_smartcard,
    _debug_dump_jws,
    _resolve_signing_method,
    add_signature,
)
