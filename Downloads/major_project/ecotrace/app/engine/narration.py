"""Narration Confidence engine (checks a generated narrative against verified evidence).

Pure: dataclasses in, dataclasses out. Narration Confidence is separate from the
Evidence Trust Score and is never blended into one number.

MF#3: force_review_flags — same mechanism as evidence engine. Non-empty list
downgrades auto_issued → hitl. Supported narration flags:
  stale_rule    — narration cites superseded regulation version
  gaming_flag   — clustering of soft-score gaming patterns
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.config import NARRATION_AUTO_ISSUED_MIN, NARRATION_HITL_MIN, NARRATION_WEIGHTS


@dataclass
class NarrationInputs:
    sanitizer_passed: bool
    numeric_verification_passed: bool
    uniqueness_check_passed: bool
    regulatory_grounding: float
    cross_document_consistency: float
    chronological_consistency: float
    no_gaming_flags: float
    corpus_version: str
    # MF#3: force-review flags — non-empty downgrades auto_issued → hitl
    force_review_flags: list = field(default_factory=list)


@dataclass
class NarrationResult:
    hard_gates: dict
    soft_scores: dict
    score: Optional[float]
    decision: str
    reason: str
    corpus_version: str
    force_review_flags: list = field(default_factory=list)


def classify_narration(score: float) -> str:
    """Classify a narration score into a decision (auto_issued / hitl / rejected)."""
    if score >= NARRATION_AUTO_ISSUED_MIN:
        return "auto_issued"
    if score >= NARRATION_HITL_MIN:
        return "hitl"
    return "rejected"


def compute_narration(inputs: NarrationInputs) -> NarrationResult:
    corpus_version = inputs.corpus_version.strip()
    if not corpus_version:
        raise ValueError("corpus_version")

    hard_gates = {
        "sanitizer_passed": inputs.sanitizer_passed,
        "numeric_verification_passed": inputs.numeric_verification_passed,
        "uniqueness_check_passed": inputs.uniqueness_check_passed,
    }
    soft_scores = {
        "regulatory_grounding": inputs.regulatory_grounding,
        "cross_document_consistency": inputs.cross_document_consistency,
        "chronological_consistency": inputs.chronological_consistency,
        "no_gaming_flags": inputs.no_gaming_flags,
    }

    failed_gates = [k for k, v in hard_gates.items() if not v]
    if failed_gates:
        return NarrationResult(
            hard_gates=hard_gates,
            soft_scores=soft_scores,
            score=None,
            decision="rejected",
            reason="gate_failed: " + ", ".join(failed_gates),
            corpus_version=corpus_version,
            force_review_flags=inputs.force_review_flags,
        )

    score    = round(sum(NARRATION_WEIGHTS[k] * soft_scores[k] for k in soft_scores), 4)
    decision = classify_narration(score)
    flags    = list(inputs.force_review_flags)

    # MF#3: downgrade auto_issued → hitl if any force-review flag is set
    if decision == "auto_issued" and flags:
        decision = "hitl"
        reason   = "force_review: " + ", ".join(flags)
    else:
        reason = decision

    return NarrationResult(
        hard_gates=hard_gates,
        soft_scores=soft_scores,
        score=score,
        decision=decision,
        reason=reason,
        corpus_version=corpus_version,
        force_review_flags=flags,
    )
