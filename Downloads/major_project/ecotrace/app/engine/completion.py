"""Completion gate engine.

Pure: dataclasses in, dataclasses out. A failed gate means HOLD for human review,
never rejection. The engine only reports passed/reasons.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from app.config import COMPLETION_WINDOW_HOURS, INVOICE_WEIGHT_TOLERANCE

_WINDOW = timedelta(hours=COMPLETION_WINDOW_HOURS)


@dataclass
class CompletionInputs:
    intake_at: datetime
    submitted_at: Optional[datetime] = None
    evidence_type: Optional[str] = None
    facility_registration_active_now: bool = False
    inter_state: bool = False
    manifest_present: bool = False
    invoice_weight_kg: Optional[float] = None
    weighbridge_weight_kg: Optional[float] = None
    invoice_buyer_id: Optional[str] = None
    facility_id: str = ""


@dataclass
class CompletionResult:
    passed: bool
    failure_reasons: list
    checks: dict


def compute_completion(inputs: CompletionInputs) -> CompletionResult:
    checks = {}
    reasons = []

    # 1. completion_evidence_submitted
    evidence_submitted = inputs.evidence_type is not None and inputs.submitted_at is not None
    checks["completion_evidence_submitted"] = evidence_submitted
    if not evidence_submitted:
        reasons.append("completion_evidence_missing")

    # 2. within_window (skip if evidence missing; counts as passed when N/A)
    if evidence_submitted:
        delta = inputs.submitted_at - inputs.intake_at
        within = (delta >= timedelta(0)) and (delta <= _WINDOW)
        checks["within_window"] = within
        if not within:
            reasons.append("within_window")
    else:
        checks["within_window"] = True  # not applicable -> passed

    # 3. facility_registration_revalidated
    checks["facility_registration_revalidated"] = inputs.facility_registration_active_now
    if not inputs.facility_registration_active_now:
        reasons.append("facility_registration_not_revalidated")

    # 4. inter_state_manifest_present (applies only if inter_state)
    if inputs.inter_state:
        checks["inter_state_manifest_present"] = inputs.manifest_present
        if not inputs.manifest_present:
            reasons.append("manifest_missing")
    else:
        checks["inter_state_manifest_present"] = True

    # 5. invoice_weight_consistent (applies only if evidence_type in sales_invoice/both)
    invoice_applies = inputs.evidence_type in ("sales_invoice", "both")
    if invoice_applies:
        if inputs.invoice_weight_kg is None or inputs.weighbridge_weight_kg is None:
            checks["invoice_weight_consistent"] = False
            reasons.append("invoice_weight_unverifiable")
        else:
            tol = INVOICE_WEIGHT_TOLERANCE * inputs.weighbridge_weight_kg
            ok = abs(inputs.invoice_weight_kg - inputs.weighbridge_weight_kg) <= tol
            checks["invoice_weight_consistent"] = ok
            if not ok:
                reasons.append("invoice_weight_inconsistent")
    else:
        checks["invoice_weight_consistent"] = True

    # 6. invoice_buyer_not_related (applies if buyer provided)
    if inputs.invoice_buyer_id is not None:
        ok = inputs.invoice_buyer_id != inputs.facility_id
        checks["invoice_buyer_not_related"] = ok
        if not ok:
            reasons.append("invoice_buyer_related_to_facility")
    else:
        checks["invoice_buyer_not_related"] = True

    passed = all(checks.values())
    return CompletionResult(passed=passed, failure_reasons=reasons, checks=checks)
