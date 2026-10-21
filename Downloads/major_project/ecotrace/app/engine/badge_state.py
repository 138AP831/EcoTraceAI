"""Badge state machine (pure).

Pure: dataclasses in, dataclasses out. No sqlalchemy/fastapi/app.models.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from app.config import REVOCATION_GRACE_DAYS


class BadgeStateError(Exception):
    pass


@dataclass
class ObligationReopen:
    weight_kg: float
    grace_until: datetime


@dataclass
class RevokeEffect:
    new_status: str
    obligation_reopen: Optional[ObligationReopen]


def can_issue_badge(collection_status, narration_decision, hitl_approved=False) -> bool:
    """True iff (completion_passed + auto_issued) or (narration_hitl + hitl_approved)."""
    if collection_status == "completion_passed" and narration_decision == "auto_issued":
        return True
    if collection_status == "narration_hitl" and hitl_approved is True:
        return True
    return False


def next_status_on_reference(badge_status) -> str:
    """unconsumed -> consumed; raises if already consumed or revoked."""
    if badge_status in ("consumed", "revoked"):
        raise BadgeStateError(f"cannot reference a {badge_status} badge")
    return "consumed"


def revoke(badge_status, weight_kg, now: datetime) -> RevokeEffect:
    """Revoke a badge. Raises if already revoked.

    obligation_reopen present only if badge was consumed (a reference existed).
    """
    if badge_status == "revoked":
        raise BadgeStateError("badge already revoked")
    obligation_reopen = None
    if badge_status == "consumed":
        obligation_reopen = ObligationReopen(
            weight_kg=weight_kg,
            grace_until=now + timedelta(days=REVOCATION_GRACE_DAYS),
        )
    return RevokeEffect(new_status="revoked", obligation_reopen=obligation_reopen)
