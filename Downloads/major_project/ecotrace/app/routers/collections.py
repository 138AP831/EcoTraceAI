"""Collection, picker, evidence, completion, narration and hitl endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.badge_state import can_issue_badge
from app.engine.completion import CompletionInputs, compute_completion
from app.engine.evidence import EvidenceInputs, compute_evidence
from app.engine.narration import NarrationInputs, compute_narration
from app.models import Collection, Facility, Picker, TrustBadge
from app.schemas import (
    CollectionCreate,
    CollectionOut,
    CompletionRequest,
    EvidenceRequest,
    HitlApproveRequest,
    NarrationRequest,
    PickerCreate,
    PickerOut,
)
from app.services import create_badge, latest_completion, latest_evidence, latest_narration, write_audit

router = APIRouter(tags=["collections"])

_EVIDENCE_STATUS = {"auto_verified": "evidence_verified", "hitl": "evidence_hitl", "rejected": "evidence_rejected"}
_NARRATION_STATUS = {"auto_issued": "badge_issued", "hitl": "narration_hitl", "rejected": "narration_rejected"}


# ---------------- Pickers ----------------
@router.post("/pickers", response_model=PickerOut, status_code=status.HTTP_201_CREATED)
def create_picker(payload: PickerCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    picker = Picker(**data)
    db.add(picker)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="picker_phone_unique_violation")
    db.refresh(picker)
    return picker


@router.get("/pickers/{picker_id}", response_model=PickerOut)
def get_picker(picker_id: str, db: Session = Depends(get_db)):
    picker = db.get(Picker, picker_id)
    if not picker:
        raise HTTPException(status_code=404, detail="picker_not_found")
    return picker


# ---------------- Collections ----------------
@router.post("/collections", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
def create_collection(payload: CollectionCreate, db: Session = Depends(get_db)):
    facility = db.get(Facility, payload.facility_id)
    if not facility:
        raise HTTPException(status_code=422, detail="facility_not_found")
    picker = db.get(Picker, payload.picker_id)
    if not picker:
        raise HTTPException(status_code=422, detail="picker_not_found")

    data = payload.model_dump(exclude_unset=True)
    data["facility_state"] = facility.state
    data["inter_state"] = payload.collection_state != facility.state
    if data.get("intake_at") is None:
        data["intake_at"] = datetime.utcnow()
    collection = Collection(**data)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection


@router.get("/collections/{collection_id}")
def get_collection(collection_id: str, db: Session = Depends(get_db)):
    collection = db.get(Collection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="collection_not_found")

    ev = latest_evidence(db, collection_id)
    comp = latest_completion(db, collection_id)
    nar = latest_narration(db, collection_id)
    badge = db.query(TrustBadge).filter(TrustBadge.collection_id == collection_id).first()

    def _dt(v):
        return v.isoformat() if isinstance(v, (datetime,)) else v

    out = CollectionOut.model_validate(collection).model_dump()
    out["evidence"] = _serialize_evidence(ev) if ev else None
    out["completion"] = _serialize_completion(comp) if comp else None
    out["narration"] = _serialize_narration(nar) if nar else None
    out["badge"] = (
        {"id": badge.id, "status": badge.status, "evidence_score": badge.evidence_score,
         "narration_score": badge.narration_score, "weight_kg": badge.weight_kg,
         "issued_at": _dt(badge.issued_at)}
        if badge else None
    )
    return out


def _serialize_evidence(ev):
    return {
        "id": ev.id, "mode": ev.mode, "component_scores": ev.component_scores,
        "gates": ev.gates, "score": ev.score, "decision": ev.decision,
        "reason": ev.reason, "weight_source": ev.weight_source,
    }


def _serialize_completion(comp):
    return {
        "id": comp.id, "evidence_type": comp.evidence_type,
        "submitted_at": comp.submitted_at.isoformat() if comp.submitted_at else None,
        "invoice_weight_kg": comp.invoice_weight_kg, "invoice_buyer_id": comp.invoice_buyer_id,
        "facility_revalidated": comp.facility_revalidated, "manifest_present": comp.manifest_present,
        "passed": comp.passed, "failure_reasons": comp.failure_reasons,
    }


def _serialize_narration(nar):
    return {
        "id": nar.id, "hard_gates": nar.hard_gates, "soft_scores": nar.soft_scores,
        "score": nar.score, "decision": nar.decision, "reason": nar.reason,
        "corpus_version": nar.corpus_version, "sanitizer_passed": nar.sanitizer_passed,
    }


# ---------------- Evidence ----------------
@router.post("/collections/{collection_id}/evidence", status_code=status.HTTP_201_CREATED)
def assess_evidence(collection_id: str, payload: EvidenceRequest, db: Session = Depends(get_db)):
    collection = db.get(Collection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="collection_not_found")
    if collection.status != "submitted":
        raise HTTPException(status_code=409, detail=f"evidence_not_allowed_from_status:{collection.status}")

    fields = payload.model_dump()
    inputs = EvidenceInputs(item_state=collection.item_state, **fields)
    try:
        result = compute_evidence(inputs)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"invalid_field:{e}")

    from app.models import EvidenceAssessment

    mode = "A" if collection.item_state == "intact" else "B"
    ea = EvidenceAssessment(
        collection_id=collection_id,
        mode=mode,
        component_scores=result.component_scores,
        gates=result.gates,
        score=result.score,
        decision=result.decision,
        reason=result.reason,
        weight_source=result.weight_source,
    )
    db.add(ea)
    collection.status = _EVIDENCE_STATUS[result.decision]
    db.flush()
    write_audit(db, "collection", collection_id, "evidence_assessed",
                {"decision": result.decision, "score": result.score})
    db.commit()
    db.refresh(ea)
    return _serialize_evidence(ea) | {"collection_status": collection.status}


# ---------------- Completion ----------------
@router.post("/collections/{collection_id}/completion", status_code=status.HTTP_201_CREATED)
def assess_completion(collection_id: str, payload: CompletionRequest, db: Session = Depends(get_db)):
    collection = db.get(Collection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="collection_not_found")
    if collection.status not in ("evidence_verified", "completion_hold"):
        raise HTTPException(status_code=409, detail=f"completion_not_allowed_from_status:{collection.status}")

    inputs = CompletionInputs(
        intake_at=collection.intake_at,
        submitted_at=payload.submitted_at,
        evidence_type=payload.evidence_type,
        facility_registration_active_now=payload.facility_registration_active_now,
        inter_state=collection.inter_state,
        manifest_present=payload.manifest_present,
        invoice_weight_kg=payload.invoice_weight_kg,
        weighbridge_weight_kg=collection.weighbridge_weight_kg,
        invoice_buyer_id=payload.invoice_buyer_id,
        facility_id=collection.facility_id,
    )
    result = compute_completion(inputs)

    from app.models import CompletionRecord

    cr = CompletionRecord(
        collection_id=collection_id,
        evidence_type=payload.evidence_type,
        submitted_at=payload.submitted_at,
        invoice_weight_kg=payload.invoice_weight_kg,
        invoice_buyer_id=payload.invoice_buyer_id,
        facility_revalidated=payload.facility_registration_active_now,
        manifest_present=payload.manifest_present,
        passed=result.passed,
        failure_reasons=result.failure_reasons,
    )
    db.add(cr)
    collection.status = "completion_passed" if result.passed else "completion_hold"
    db.flush()
    write_audit(db, "collection", collection_id, "completion_assessed",
                {"passed": result.passed, "failure_reasons": result.failure_reasons})
    db.commit()
    db.refresh(cr)
    return _serialize_completion(cr) | {"collection_status": collection.status}


# ---------------- Narration ----------------
@router.post("/collections/{collection_id}/narration", status_code=status.HTTP_201_CREATED)
def assess_narration(collection_id: str, payload: NarrationRequest, db: Session = Depends(get_db)):
    collection = db.get(Collection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="collection_not_found")
    if collection.status != "completion_passed":
        raise HTTPException(status_code=409, detail=f"narration_not_allowed_from_status:{collection.status}")

    inputs = NarrationInputs(
        sanitizer_passed=payload.sanitizer_passed,
        numeric_verification_passed=payload.numeric_verification_passed,
        uniqueness_check_passed=payload.uniqueness_check_passed,
        regulatory_grounding=payload.regulatory_grounding,
        cross_document_consistency=payload.cross_document_consistency,
        chronological_consistency=payload.chronological_consistency,
        no_gaming_flags=payload.no_gaming_flags,
        corpus_version=payload.corpus_version,
    )
    try:
        result = compute_narration(inputs)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"invalid_field:{e}")

    from app.models import NarrationAssessment

    na = NarrationAssessment(
        collection_id=collection_id,
        hard_gates=result.hard_gates,
        soft_scores=result.soft_scores,
        score=result.score,
        decision=result.decision,
        reason=result.reason,
        corpus_version=result.corpus_version,
        sanitizer_passed=payload.sanitizer_passed,
    )
    db.add(na)

    badge_id = None
    if result.decision == "auto_issued":
        collection.status = "badge_issued"
        db.flush()
        badge = create_badge(db, collection, result.score)
        badge_id = badge.id
        write_audit(db, "badge", badge_id, "badge_issued", {"collection_id": collection_id})
    else:
        collection.status = _NARRATION_STATUS[result.decision]

    write_audit(db, "collection", collection_id, "narration_assessed",
                {"decision": result.decision, "score": result.score})
    db.commit()
    db.refresh(na)
    out = _serialize_narration(na)
    out["badge_id"] = badge_id
    out["collection_status"] = collection.status
    return out


# ---------------- HITL approve ----------------
@router.post("/collections/{collection_id}/hitl-approve")
def hitl_approve(collection_id: str, payload: HitlApproveRequest, db: Session = Depends(get_db)):
    collection = db.get(Collection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="collection_not_found")

    stage = payload.stage
    approved = payload.approved
    badge_id = None

    if stage == "evidence":
        if collection.status != "evidence_hitl":
            raise HTTPException(status_code=409, detail=f"hitl_evidence_not_allowed_from_status:{collection.status}")
        collection.status = "evidence_verified" if approved else "evidence_rejected"
        write_audit(db, "collection", collection_id, "hitl_approve", {"stage": "evidence", "approved": approved})
    elif stage == "narration":
        if collection.status != "narration_hitl":
            raise HTTPException(status_code=409, detail=f"hitl_narration_not_allowed_from_status:{collection.status}")
        badge_id = None
        if approved:
            collection.status = "badge_issued"
            nar = latest_narration(db, collection_id)
            db.flush()
            badge = create_badge(db, collection, nar.score if nar else None)
            badge_id = badge.id
            write_audit(db, "badge", badge_id, "badge_issued", {"collection_id": collection_id})
        else:
            collection.status = "narration_rejected"
        write_audit(db, "collection", collection_id, "hitl_approve", {"stage": "narration", "approved": approved})
    else:
        raise HTTPException(status_code=422, detail="invalid_stage")

    db.commit()
    return {"collection_id": collection_id, "stage": stage, "approved": approved,
            "new_status": collection.status, "badge_id": badge_id if stage == "narration" and approved else None}
