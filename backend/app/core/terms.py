"""Current Terms of Service + Privacy Policy version.

Bump this string when the published legal documents at
hmdigital.hr/medical/uvjeti-koristenja and hmdigital.hr/medical/pravila-privatnosti
change materially. Users whose stored terms_version is older than CURRENT_TERMS_VERSION
receive `requires_terms_acceptance: true` on login and the frontend shows a
non-dismissible consent modal.
"""

from app.models.user import User

CURRENT_TERMS_VERSION = "2026-04-24"


def requires_terms_acceptance(user: User | None) -> bool:
    if user is None:
        return False
    return user.terms_version != CURRENT_TERMS_VERSION
