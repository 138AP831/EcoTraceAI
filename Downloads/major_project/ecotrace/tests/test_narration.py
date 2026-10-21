"""Narration engine unit tests (pure, no DB)."""
import pytest

from app.engine.narration import NarrationInputs, classify_narration, compute_narration


def _base(**overrides):
    base = dict(
        sanitizer_passed=True,
        numeric_verification_passed=True,
        uniqueness_check_passed=True,
        regulatory_grounding=0.91,
        cross_document_consistency=0.95,
        chronological_consistency=1.0,
        no_gaming_flags=1.0,
        corpus_version="corpus-v1",
    )
    base.update(overrides)
    return NarrationInputs(**base)


def test_auto_issued_high_scores():
    r = compute_narration(_base(regulatory_grounding=0.91, cross_document_consistency=0.95,
                               chronological_consistency=1.0, no_gaming_flags=1.0))
    expected = round(0.35 * 0.91 + 0.30 * 0.95 + 0.20 * 1.0 + 0.15 * 1.0, 4)
    assert r.score == expected  # 0.9535
    assert r.decision == "auto_issued"


def test_hitl_mid_scores():
    r = compute_narration(_base(regulatory_grounding=0.65, cross_document_consistency=0.70,
                                chronological_consistency=0.80, no_gaming_flags=0.75))
    expected = round(0.35 * 0.65 + 0.30 * 0.70 + 0.20 * 0.80 + 0.15 * 0.75, 4)
    assert r.score == expected  # 0.71
    assert r.decision == "hitl"


def test_rejected_low_scores():
    r = compute_narration(_base(regulatory_grounding=0.50, cross_document_consistency=0.55,
                                chronological_consistency=0.60, no_gaming_flags=0.70))
    expected = round(0.35 * 0.50 + 0.30 * 0.55 + 0.20 * 0.60 + 0.15 * 0.70, 4)
    assert r.score == expected  # 0.565
    assert r.decision == "rejected"


def test_numeric_gate_false_rejected():
    r = compute_narration(_base(numeric_verification_passed=False))
    assert r.score is None
    assert r.decision == "rejected"
    assert "numeric_verification_passed" in r.reason


def test_sanitizer_passed_false_rejected():
    r = compute_narration(_base(sanitizer_passed=False))
    assert r.score is None
    assert r.decision == "rejected"
    assert "sanitizer_passed" in r.reason


def test_blank_corpus_version_raises():
    with pytest.raises(ValueError, match="corpus_version"):
        compute_narration(_base(corpus_version="   "))


def test_classify_narration_boundaries():
    assert classify_narration(0.85) == "auto_issued"
    assert classify_narration(0.60) == "hitl"
    assert classify_narration(0.5999) == "rejected"
