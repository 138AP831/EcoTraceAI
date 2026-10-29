"""Badge reference and revocation endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.badge_state import BadgeStateError, revoke
from app.models import BadgeReference, ObligationRecord, TrustBadge
from app.schemas import ReferenceRequest, RevokeRequest
from app.services import write_audit

router = APIRouter(prefix="/badges", tags=["badges"])


@router.post("/{badge_id}/reference", status_code=status.HTTP_201_CREATED)
def reference_badge(badge_id: str, payload: ReferenceRequest, db: Session = Depends(get_db)):
    badge = db.get(TrustBadge, badge_id)
    if not badge:
        raise HTTPException(status_code=404, detail="badge_not_found")
    if badge.status != "unconsumed":
        raise HTTPException(status_code=409, detail=f"badge_not_unconsumed:{badge.status}")

    obligation = db.get(ObligationRecord, payload.obligation_id)
    if not obligation:
        raise HTTPException(status_code=404, detail="obligation_not_found")
    if obligation.producer_id != payload.producer_id:
        raise HTTPException(status_code=422, detail="obligation_does_not_belong_to_producer")
    if obligation.category != badge.category:
        raise HTTPException(status_code=409, detail="category_mismatch")

    existing = db.query(BadgeReference).filter(BadgeReference.badge_id == badge_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="badge_already_referenced")

    # MF#14: obligation ceiling — badge weight must not exceed remaining obligation
    remaining = obligation.target_kg - obligation.fulfilled_kg
    if badge.weight_kg > remaining:
        raise HTTPException(
            status_code=409,
            detail=(
                f"obligation_ceiling_exceeded:"
                f"badge_weight={badge.weight_kg:.3f}kg "
                f"remaining={remaining:.3f}kg"
            ),
        )

    ref = BadgeReference(
        badge_id=badge_id,
        producer_id=payload.producer_id,
        obligation_id=payload.obligation_id,
        referenced_at=datetime.utcnow(),
        weight_kg_applied=badge.weight_kg,
    )
    db.add(ref)
    badge.status = "consumed"
    obligation.fulfilled_kg += badge.weight_kg
    db.flush()
    write_audit(db, "badge", badge_id, "badge_referenced",
                {"producer_id": payload.producer_id, "obligation_id": payload.obligation_id,
                 "weight_kg": badge.weight_kg})
    db.commit()
    db.refresh(ref)
    return {
        "badge_id": badge_id,
        "badge_status": badge.status,
        "obligation_id": payload.obligation_id,
        "obligation_fulfilled_kg": obligation.fulfilled_kg,
        "referenced_at": ref.referenced_at.isoformat(),
        "weight_kg_applied": ref.weight_kg_applied,
    }


@router.post("/{badge_id}/revoke")
def revoke_badge(badge_id: str, payload: RevokeRequest, db: Session = Depends(get_db)):
    badge = db.get(TrustBadge, badge_id)
    if not badge:
        raise HTTPException(status_code=404, detail="badge_not_found")

    try:
        effect = revoke(badge.status, badge.weight_kg, datetime.utcnow())
    except BadgeStateError:
        raise HTTPException(status_code=409, detail=f"badge_cannot_be_revoked:{badge.status}")

    grace_until = None
    ref = db.query(BadgeReference).filter(BadgeReference.badge_id == badge_id).first()
    if ref is not None:
        obligation = db.get(ObligationRecord, ref.obligation_id)
        if obligation is not None:
            obligation.fulfilled_kg = max(0.0, obligation.fulfilled_kg - badge.weight_kg)
        if effect.obligation_reopen is not None:
            grace_until = effect.obligation_reopen.grace_until

    badge.status = "revoked"
    badge.revoked_at = datetime.utcnow()
    badge.revocation_reason = payload.reason
    db.flush()
    write_audit(db, "badge", badge_id, "badge_revoked",
                {"reason": payload.reason, "obligation_reopen": grace_until is not None})
    db.commit()
    db.refresh(badge)
    return {
        "badge_id": badge_id,
        "new_status": badge.status,
        "grace_until": grace_until.isoformat() if grace_until else None,
        "obligation_reopen": grace_until is not None,
    }
