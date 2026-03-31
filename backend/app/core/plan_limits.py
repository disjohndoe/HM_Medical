from dataclasses import dataclass


@dataclass(frozen=True)
class PlanLimits:
    max_users: int
    max_patients: int | None  # None = unlimited
    max_concurrent_sessions: int
    cezih_access: bool


PLAN_LIMITS: dict[str, PlanLimits] = {
    "trial": PlanLimits(
        max_users=1,
        max_patients=50,
        max_concurrent_sessions=1,
        cezih_access=True,
    ),
    "solo": PlanLimits(
        max_users=2,  # Website promises "1-2 korisnika" — must match
        max_patients=None,
        max_concurrent_sessions=2,
        cezih_access=True,
    ),
    "poliklinika": PlanLimits(
        max_users=5,
        max_patients=None,
        max_concurrent_sessions=5,
        cezih_access=True,
    ),
    "poliklinika_plus": PlanLimits(
        max_users=15,
        max_patients=None,
        max_concurrent_sessions=15,
        cezih_access=True,
    ),
}


def get_plan_limits(plan_tier: str) -> PlanLimits:
    return PLAN_LIMITS.get(plan_tier, PLAN_LIMITS["trial"])
