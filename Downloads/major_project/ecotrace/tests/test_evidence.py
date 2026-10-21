"""Evidence engine unit tests (pure, no DB)."""
import pytest

from app.engine.evidence import EvidenceInputs, classify_evidence, compute_evidence


def _mode_a(**overrides):
    base = dict(
        item_state="intact",
        duplicate_detected=False,
        facility_registration_active=True,
        device_serial_confidence=1.0,
        serial_uniqueness=1.0,
        facility_registration_validity=1.0,
        gps_validity=1.0,
        image_quality=1.0,
        declared_weight_consistency=1.0,
        weighbridge_weight_consistency=1.0,
    )
    base.update(overrides)
    return EvidenceInputs(**base)


def _mode_b(**overrides):
    base = dict(
        item_state="dismantled",
        duplicate_detected=False,
        facility_registration_active=True,
        component_classification_confidence=1.0,
        material_composition_plausibility=1.0,
        facility_registration_validity=1.0,
        gps_validity=1.0,
        image_quality=1.0,
        declared_weight_consistency=1.0,
        weighbridge_weight_consistency=1.0,
    )
    base.update(overrides)
    return EvidenceInputs(**base)


def test_mode_a_all_signals_one():
    r = compute_evidence(_mode_a())
    assert r.score == 1.0
    assert r.decision == "auto_verified"
    assert r.weight_source == "weighbridge"


def test_mode_b_all_signals_one():
    r = compute_evidence(_mode_b())
    assert r.score == 1.0
    assert r.decision == "auto_verified"


def test_mode_a_ignores_mode_b_fields():
    base = _mode_a()
    r1 = compute_evidence(base)
    # garbage Mode B fields in [0,1] must not change Mode A score
    r2 = compute_evidence(_mode_a(component_classification_confidence=0.12,
                                  material_composition_plausibility=0.99))
    assert r1.score == r2.score
    assert r2.decision == "auto_verified"


def test_mode_b_ignores_mode_a_fields():
    r1 = compute_evidence(_mode_b())
    r2 = compute_evidence(_mode_b(device_serial_confidence=0.10, serial_uniqueness=0.99))
    assert r1.score == r2.score


def test_missing_required_mode_a_field():
    with pytest.raises(ValueError, match="device_serial_confidence"):
        compute_evidence(EvidenceInputs(
            item_state="intact", duplicate_detected=False, facility_registration_active=True,
            serial_uniqueness=1.0, facility_registration_validity=1.0,
            gps_validity=1.0, image_quality=1.0, declared_weight_consistency=1.0,
        ))


def test_worked_example_weighbridge():
    r = compute_evidence(_mode_a(
        device_serial_confidence=0.92, serial_uniqueness=1.0,
        facility_registration_validity=1.0, gps_validity=0.95, image_quality=0.88,
        weighbridge_weight_consistency=0.90,
    ))
    expected = round(0.30 * 0.92 + 0.15 * 1.0 + 0.20 * 1.0 + 0.15 * 0.95
                     + 0.10 * 0.88 + 0.10 * 0.90, 4)
    assert r.score == expected  # 0.9465
    assert r.decision == "auto_verified"
    assert r.weight_source == "weighbridge"


def test_worked_example_declared_discounted():
    r = compute_evidence(_mode_a(
        device_serial_confidence=0.92, serial_uniqueness=1.0,
        facility_registration_validity=1.0, gps_validity=0.95, image_quality=0.88,
        weighbridge_weight_consistency=None, declared_weight_consistency=0.90,
    ))
    expected = round(0.30 * 0.92 + 0.15 * 1.0 + 0.20 * 1.0 + 0.15 * 0.95
                     + 0.10 * 0.88 + 0.10 * (0.90 * 0.85), 4)
    assert r.score == expected  # 0.933
    assert r.weight_source == "declared_discounted"


def test_duplicate_detected_rejected():
    r = compute_evidence(_mode_a(duplicate_detected=True))
    assert r.score is None
    assert r.decision == "rejected"
    assert "no_duplicate" in r.reason


def test_facility_registration_inactive_rejected():
    r = compute_evidence(_mode_a(facility_registration_active=False))
    assert r.score is None
    assert r.decision == "rejected"
    assert "facility_registration_active" in r.reason


def test_classify_evidence_boundaries():
    assert classify_evidence(0.80) == "auto_verified"
    assert classify_evidence(0.7999) == "hitl"
    assert classify_evidence(0.55) == "hitl"
    assert classify_evidence(0.5499) == "rejected"


def test_out_of_range_raises():
    with pytest.raises(ValueError, match="gps_validity"):
        compute_evidence(_mode_a(gps_validity=1.2))
