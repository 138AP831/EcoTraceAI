"""Configuration constants for EcoTrace AI.

All weights/thresholds/windows live ONLY here. The pure engine modules import
these constants; they never hardcode numeric literals.
"""

# --- Evidence weights (Mode A, intact) sums to 1.0 ---
EVIDENCE_WEIGHTS_INTACT = {
    "device_serial_confidence": 0.30,
    "serial_uniqueness": 0.15,
    "facility_registration_validity": 0.20,
    "gps_validity": 0.15,
    "image_quality": 0.10,
    "weight_consistency": 0.10,
}

# --- Evidence weights (Mode B, dismantled) sums to 1.0 ---
EVIDENCE_WEIGHTS_DISMANTLED = {
    "component_classification_confidence": 0.30,
    "material_composition_plausibility": 0.15,
    "facility_registration_validity": 0.20,
    "gps_validity": 0.15,
    "image_quality": 0.10,
    "weight_consistency": 0.10,
}

# score >= 0.80 auto_verified; 0.55 <= score < 0.80 hitl; score < 0.55 rejected
EVIDENCE_AUTO_VERIFIED_MIN = 0.80
EVIDENCE_HITL_MIN = 0.55

# --- Narration weights sums to 1.0 ---
NARRATION_WEIGHTS = {
    "regulatory_grounding": 0.35,
    "cross_document_consistency": 0.30,
    "chronological_consistency": 0.20,
    "no_gaming_flags": 0.15,
}

# score >= 0.85 auto_issued; 0.60 <= score < 0.85 hitl; score < 0.60 rejected
NARRATION_AUTO_ISSUED_MIN = 0.85
NARRATION_HITL_MIN = 0.60

UNVERIFIED_WEIGHT_DISCOUNT = 0.85
INVOICE_WEIGHT_TOLERANCE = 0.05
COMPLETION_WINDOW_HOURS = 72
REVOCATION_GRACE_DAYS = 30

# Import-time assertions: each weight set must sum to 1.0 (tolerance 1e-9).
assert abs(sum(EVIDENCE_WEIGHTS_INTACT.values()) - 1.0) <= 1e-9, "EVIDENCE_WEIGHTS_INTACT must sum to 1.0"
assert abs(sum(EVIDENCE_WEIGHTS_DISMANTLED.values()) - 1.0) <= 1e-9, "EVIDENCE_WEIGHTS_DISMANTLED must sum to 1.0"
assert abs(sum(NARRATION_WEIGHTS.values()) - 1.0) <= 1e-9, "NARRATION_WEIGHTS must sum to 1.0"
