"""Marketplace listing of trust badges."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Facility, TrustBadge
from app.schemas import MarketplaceBadgeOut

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@router.get("/badges", response_model=list[MarketplaceBadgeOut])
def list_badges(
    min_evidence_score: float | None = None,
    category: str | None = None,
    state: str | None = None,
    issued_from: str | None = None,
    issued_to: str | None = None,
    status: str | None = None,
    sort: str = "score_desc",
    db: Session = Depends(get_db),
):
    from datetime import datetime

    from app.schemas import _to_naive_utc

    badge_status = status if status is not None else "unconsumed"

    q = db.query(TrustBadge).join(Facility, TrustBadge.facility_id == Facility.id)
    q = q.filter(TrustBadge.status == badge_status)

    if min_evidence_score is not None:
        q = q.filter(TrustBadge.evidence_score >= min_evidence_score)
    if category is not None:
        q = q.filter(TrustBadge.category == category)
    if state is not None:
        q = q.filter(Facility.state == state)
    if issued_from is not None:
        q = q.filter(TrustBadge.issued_at >= _to_naive_utc(issued_from))
    if issued_to is not None:
        q = q.filter(TrustBadge.issued_at <= _to_naive_utc(issued_to))

    if sort == "newest":
        q = q.order_by(TrustBadge.issued_at.desc(), TrustBadge.id.desc())
    else:
        q = q.order_by(TrustBadge.evidence_score.desc(), TrustBadge.id.desc())

    badges = q.all()
    fac_states = {f.id: f.state for f in db.query(Facility).all()}
    return [
        MarketplaceBadgeOut(
            id=b.id,
            collection_id=b.collection_id,
            facility_id=b.facility_id,
            facility_state=fac_states.get(b.facility_id, ""),
            category=b.category,
            weight_kg=b.weight_kg,
            evidence_score=b.evidence_score,
            narration_score=b.narration_score,
            status=b.status,
            issued_at=b.issued_at,
        )
        for b in badges
    ]
