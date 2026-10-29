"""Evidence Trust Score engine (physical-event verification, non-GenAI).

Pure: dataclasses in, dataclasses out. No sqlalchemy/fastapi/app.models.
Weights/thresholds come from app.config only (no literals here).

MF#3: force_review_flags — a list of flag strings that, if non-empty, downgrade
an auto_verified decision to hitl regardless of the numeric score.
Flags are set by upstream signal processing (CV/GPS/timestamp checks) before
the engine is called; the engine itself never sets them.

Supported flags (all lower_snake_case):
  gps_spoof          — two GPS readings 200+ km apart within 10 min
  timestamp_mismatch — photo EXIF timestamp differs from intake by > 8h
  wrong_facility_slip — weighbridge slip from a different facility
  unknown_category   — device category not in authorised list
  gaming_flag        — clustering of soft-score gaming signals
  stale_rule         — narration cites a superseded regulation version
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.config import (
    EVIDENCE_AUTO_VERIFIED_MIN,
    EVIDENCE_HITL_MIN,
    EVIDENCE_WEIGHTS_DISMANTLED,
    EVIDENCE_WEIGHTS_INTACT,
    UNVERIFIED_WEIGHT_DISCOUNT,
)

# Float signal fields that must be validated to [0, 1] when provided.
_FLOAT_FIELDS = (
    "device_serial_confidence",
    "serial_uniqueness",
    "component_classification_confidence",
    "material_composition_plausibility",
    "facility_registration_validity",
    "gps_validity",
    "image_quality",
    "declared_weight_consistency",
    "weighbridge_weight_consistency",
)


@dataclass
class EvidenceInputs:
    item_state: str
    duplicate_detected: bool
    facility_registration_active: bool
    # Mode A only
    device_serial_confidence: Optional[float] = None
    serial_uniqueness: Optional[float] = None
    # Mode B only
    component_classification_confidence: Optional[float] = None
    material_composition_plausibility: Optional[float] = None
    # shared
    facility_registration_validity: Optional[float] = None
    gps_validity: Optional[float] = None
    image_quality: Optional[float] = None
    declared_weight_consistency: Optional[float] = None
    weighbridge_weight_consistency: Optional[float] = None
    # MF#3: force-review flags — any non-empty list downgrades auto_verified → hitl
    force_review_flags: list = field(default_factory=list)


@dataclass
class EvidenceResult:
    mode: str
    gates: dict
    gate_failures: list
    component_scores: dict
    weights: dict
    score: Optional[float]
    decision: str
    reason: str
    weight_source: Optional[str]
    # MF#3: echo back which flags were active
    force_review_flags: list = field(default_factory=list)


def classify_evidence(score: float) -> str:
    """Classify an evidence score. Boundary-inclusive on the upper band."""
    if score >= EVIDENCE_AUTO_VERIFIED_MIN:
        return "auto_verified"
    if score >= EVIDENCE_HITL_MIN:
        return "hitl"
    return "rejected"


def compute_evidence(inputs: EvidenceInputs) -> EvidenceResult:
    # 1. Validate every provided float is in [0, 1].
    for f in _FLOAT_FIELDS:
        v = getattr(inputs, f)
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError(f)

    mode = "A" if inputs.item_state == "intact" else "B"
    if mode == "A":
        weights = EVIDENCE_WEIGHTS_INTACT
        signal_fields = (
            "device_serial_confidence",
            "serial_uniqueness",
            "facility_registration_validity",
            "gps_validity",
            "image_quality",
        )
    else:
        weights = EVIDENCE_WEIGHTS_DISMANTLED
        signal_fields = (
            "component_classification_confidence",
            "material_composition_plausibility",
            "facility_registration_validity",
            "gps_validity",
            "image_quality",
        )

    # Required field set for the chosen mode must be non-None.
    for f in signal_fields:
        if getattr(inputs, f) is None:
            raise ValueError(f)

    # 2. Hard gates BEFORE scoring.
    gates = {
        "no_duplicate": not inputs.duplicate_detected,
        "facility_registration_active": inputs.facility_registration_active,
    }
    gate_failures = [k for k, v in gates.items() if not v]
    if gate_failures:
        return EvidenceResult(
            mode=mode,
            gates=gates,
            gate_failures=gate_failures,
            component_scores={},
            weights=weights,
            score=None,
            decision="rejected",
            reason="gate_failed: " + ", ".join(gate_failures),
            weight_source=None,
            force_review_flags=inputs.force_review_flags,
        )

    # 3. Weight signal.
    if inputs.weighbridge_weight_consistency is not None:
        weight_signal = inputs.weighbridge_weight_consistency
        weight_source = "weighbridge"
    elif inputs.declared_weight_consistency is not None:
        weight_signal = inputs.declared_weight_consistency * UNVERIFIED_WEIGHT_DISCOUNT
        weight_source = "declared_discounted"
    else:
        raise ValueError("declared_weight_consistency")

    # 4. Score.
    component_scores = {f: getattr(inputs, f) for f in signal_fields}
    component_scores["weight_consistency"] = weight_signal
    score = round(sum(weights[k] * component_scores[k] for k in weights), 4)

    # 5. Classify — then apply MF#3 force-review downgrade.
    decision = classify_evidence(score)
    flags    = list(inputs.force_review_flags)
    if decision == "auto_verified" and flags:
        decision = "hitl"
        reason   = "force_review: " + ", ".join(flags)
    else:
        reason = decision

    return EvidenceResult(
        mode=mode,
        gates=gates,
        gate_failures=[],
        component_scores=component_scores,
        weights=weights,
        score=score,
        decision=decision,
        reason=reason,
        weight_source=weight_source,
        force_review_flags=flags,
    )
