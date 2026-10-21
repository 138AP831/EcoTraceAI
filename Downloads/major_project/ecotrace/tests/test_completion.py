"""Completion gate engine unit tests (pure, no DB)."""
from datetime import datetime, timedelta

from app.engine.completion import CompletionInputs, compute_completion

INTAKE = datetime(2026, 6, 1, 12, 0, 0)


def _base(**overrides):
    base = dict(
        intake_at=INTAKE,
        submitted_at=INTAKE + timedelta(hours=10),
        evidence_type="destruction_media",
        facility_registration_active_now=True,
        inter_state=False,
        manifest_present=False,
        invoice_weight_kg=None,
        weighbridge_weight_kg=None,
        invoice_buyer_id=None,
        facility_id="FAC-1",
    )
    base.update(overrides)
    return CompletionInputs(**base)


def test_destruction_media_within_window_passes():
    assert compute_completion(_base(submitted_at=INTAKE + timedelta(hours=71))).passed is True
    assert compute_completion(_base(submitted_at=INTAKE + timedelta(hours=72))).passed is True


def test_destruction_media_late_fails_within_window():
    r = compute_completion(_base(submitted_at=INTAKE + timedelta(hours=73)))
    assert r.passed is False
    assert "within_window" in r.failure_reasons


def test_evidence_type_none_fails_no_exception():
    r = compute_completion(_base(evidence_type=None, submitted_at=None))
    assert r.passed is False
    assert "completion_evidence_missing" in r.failure_reasons


def test_facility_inactive_fails():
    r = compute_completion(_base(facility_registration_active_now=False))
    assert r.passed is False
    assert "facility_registration_not_revalidated" in r.failure_reasons


def test_inter_state_no_manifest_fails():
    r = compute_completion(_base(inter_state=True, manifest_present=False))
    assert r.passed is False
    assert "manifest_missing" in r.failure_reasons


def test_inter_state_with_manifest_passes():
    assert compute_completion(_base(inter_state=True, manifest_present=True)).passed is True


def test_intra_state_ignores_manifest():
    # manifest_present False but intra-state -> manifest check not applicable
    assert compute_completion(_base(inter_state=False, manifest_present=False)).passed is True


def test_invoice_weight_tolerance():
    wb = 100.0
    # 4% off passes
    assert compute_completion(
        _base(evidence_type="sales_invoice", weighbridge_weight_kg=wb, invoice_weight_kg=wb * 1.04)
    ).passed is True
    # exactly 5% passes
    assert compute_completion(
        _base(evidence_type="sales_invoice", weighbridge_weight_kg=wb, invoice_weight_kg=wb * 1.05)
    ).passed is True
    # 6% fails
    r = compute_completion(
        _base(evidence_type="sales_invoice", weighbridge_weight_kg=wb, invoice_weight_kg=wb * 1.06)
    )
    assert r.passed is False
    assert "invoice_weight_inconsistent" in r.failure_reasons


def test_invoice_missing_weighbridge_unverifiable():
    r = compute_completion(
        _base(evidence_type="sales_invoice", weighbridge_weight_kg=None, invoice_weight_kg=100.0)
    )
    assert r.passed is False
    assert "invoice_weight_unverifiable" in r.failure_reasons


def test_invoice_buyer_related_to_facility_fails():
    r = compute_completion(
        _base(evidence_type="sales_invoice", weighbridge_weight_kg=100.0,
              invoice_weight_kg=100.0, invoice_buyer_id="FAC-1", facility_id="FAC-1")
    )
    assert r.passed is False
    assert "invoice_buyer_related_to_facility" in r.failure_reasons
