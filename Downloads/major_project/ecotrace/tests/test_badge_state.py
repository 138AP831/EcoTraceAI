"""Badge state machine unit tests (pure, no DB)."""
from datetime import datetime, timedelta

import pytest

from app.engine.badge_state import (
    BadgeStateError,
    can_issue_badge,
    next_status_on_reference,
    revoke,
)

NOW = datetime(2026, 10, 20, 0, 0, 0)


def test_can_issue_auto():
    assert can_issue_badge("completion_passed", "auto_issued") is True


def test_can_issue_hitl_approved():
    assert can_issue_badge("narration_hitl", "hitl", hitl_approved=True) is True


@pytest.mark.parametrize(
    "collection_status, narration_decision, hitl_approved",
    [
        ("completion_passed", "hitl", False),
        ("completion_passed", "rejected", False),
        ("narration_hitl", "auto_issued", False),
        ("narration_hitl", "hitl", False),
        ("narration_hitl", "hitl", None),
        ("evidence_verified", "auto_issued", False),
        ("submitted", "auto_issued", True),
        ("badge_issued", "auto_issued", True),
    ],
)
def test_can_issue_false_combinations(collection_status, narration_decision, hitl_approved):
    assert can_issue_badge(collection_status, narration_decision, hitl_approved) is False


def test_next_status_on_reference_unconsumed():
    assert next_status_on_reference("unconsumed") == "consumed"


def test_next_status_on_reference_consumed_raises():
    with pytest.raises(BadgeStateError):
        next_status_on_reference("consumed")


def test_next_status_on_reference_revoked_raises():
    with pytest.raises(BadgeStateError):
        next_status_on_reference("revoked")


def test_revoke_consumed_opens_obligation():
    eff = revoke("consumed", 12.0, NOW)
    assert eff.new_status == "revoked"
    assert eff.obligation_reopen is not None
    assert eff.obligation_reopen.weight_kg == 12.0
    assert eff.obligation_reopen.grace_until == NOW + timedelta(days=30)


def test_revoke_unconsumed_no_reopen():
    eff = revoke("unconsumed", 12.0, NOW)
    assert eff.new_status == "revoked"
    assert eff.obligation_reopen is None


def test_revoke_twice_raises():
    revoke("consumed", 12.0, NOW)
    with pytest.raises(BadgeStateError):
        revoke("revoked", 12.0, NOW)
