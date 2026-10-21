"""Shared service helpers: audit logging and badge creation."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Collection,
    CompletionRecord,
    EvidenceAssessment,
    NarrationAssessment,
    TrustBadge,
)


def write_audit(db: Session, entity_type: str, entity_id: str, action: str, payload: dict | None = None):
    log = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        payload=payload or {},
        at=datetime.utcnow(),
    )
    db.add(log)


def latest_evidence(db: Session, collection_id: str):
    return (
        db.query(EvidenceAssessment)
        .filter(EvidenceAssessment.collection_id == collection_id)
        .order_by(EvidenceAssessment.created_at.desc(), EvidenceAssessment.id.desc())
        .first()
    )


def latest_completion(db: Session, collection_id: str):
    return (
        db.query(CompletionRecord)
        .filter(CompletionRecord.collection_id == collection_id)
        .order_by(CompletionRecord.created_at.desc(), CompletionRecord.id.desc())
        .first()
    )


def latest_narration(db: Session, collection_id: str):
    return (
        db.query(NarrationAssessment)
        .filter(NarrationAssessment.collection_id == collection_id)
        .order_by(NarrationAssessment.created_at.desc(), NarrationAssessment.id.desc())
        .first()
    )


def create_badge(db: Session, collection: Collection, narration_score):
    ev = latest_evidence(db, collection.id)
    weight_kg = (
        collection.weighbridge_weight_kg
        if collection.weighbridge_weight_kg is not None
        else collection.declared_weight_kg
    )
    badge = TrustBadge(
        collection_id=collection.id,
        facility_id=collection.facility_id,
        category=collection.category,
        weight_kg=weight_kg,
        evidence_score=ev.score if ev else None,
        narration_score=narration_score,
        status="unconsumed",
        issued_at=datetime.utcnow(),
    )
    db.add(badge)
    db.flush()
    return badge
