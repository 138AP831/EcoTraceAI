"""Pydantic v2 schemas. Datetimes are naive UTC everywhere.

Request bodies accept ISO strings; tz-aware inputs are converted to UTC then the
tzinfo is dropped so the engine only ever sees naive datetimes.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


def _to_naive_utc(value):
    if value is None:
        return value
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return value
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    else:
        return value
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def naive_utc() -> datetime:
    return datetime.utcnow()


# ---------------- Request schemas ----------------


class FacilityCreate(BaseModel):
    id: Optional[str] = None
    name: str
    registration_no: str
    authority: str
    state: str
    registration_status: str
    registration_valid_until: Optional[date] = None
    geofence_lat: Optional[float] = None
    geofence_lng: Optional[float] = None
    geofence_radius_m: Optional[float] = None
    authorized_categories: Optional[list[str]] = None
    daily_capacity_kg: Optional[float] = None
    booked_capacity_kg: Optional[float] = None


class PickerCreate(BaseModel):
    id: Optional[str] = None
    name: str
    phone: str


class ProducerCreate(BaseModel):
    id: Optional[str] = None
    name: str
    state: str


class ObligationCreate(BaseModel):
    id: Optional[str] = None
    category: str
    compliance_period: str
    target_kg: float


class CollectionCreate(BaseModel):
    id: Optional[str] = None
    picker_id: str
    facility_id: str
    item_state: str
    category: str
    serial_or_imei: Optional[str] = None
    declared_weight_kg: float
    weighbridge_weight_kg: Optional[float] = None
    collection_state: str
    image_hash: str
    intake_at: Optional[datetime] = None

    @field_validator("intake_at", mode="before")
    @classmethod
    def _naive_intake(cls, v):
        return _to_naive_utc(v)


class EvidenceRequest(BaseModel):
    duplicate_detected: bool
    facility_registration_active: bool
    device_serial_confidence: Optional[float] = None
    serial_uniqueness: Optional[float] = None
    component_classification_confidence: Optional[float] = None
    material_composition_plausibility: Optional[float] = None
    facility_registration_validity: Optional[float] = None
    gps_validity: Optional[float] = None
    image_quality: Optional[float] = None
    declared_weight_consistency: Optional[float] = None
    weighbridge_weight_consistency: Optional[float] = None


class CompletionRequest(BaseModel):
    submitted_at: Optional[datetime] = None
    evidence_type: Optional[str] = None
    facility_registration_active_now: bool
    manifest_present: bool
    invoice_weight_kg: Optional[float] = None
    invoice_buyer_id: Optional[str] = None

    @field_validator("submitted_at", mode="before")
    @classmethod
    def _naive_submitted(cls, v):
        return _to_naive_utc(v)


class NarrationRequest(BaseModel):
    sanitizer_passed: bool
    numeric_verification_passed: bool
    uniqueness_check_passed: bool
    regulatory_grounding: float
    cross_document_consistency: float
    chronological_consistency: float
    no_gaming_flags: float
    corpus_version: str


class HitlApproveRequest(BaseModel):
    stage: str  # "evidence" | "narration"
    approved: bool


class ReferenceRequest(BaseModel):
    producer_id: str
    obligation_id: str


class RevokeRequest(BaseModel):
    reason: str


# ---------------- Response schemas ----------------


class ORMOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FacilityOut(ORMOut):
    id: str
    name: str
    registration_no: str
    authority: str
    state: str
    registration_status: str
    registration_valid_until: Optional[date] = None
    geofence_lat: Optional[float] = None
    geofence_lng: Optional[float] = None
    geofence_radius_m: Optional[float] = None
    authorized_categories: list = []
    daily_capacity_kg: Optional[float] = None
    booked_capacity_kg: Optional[float] = None


class PickerOut(ORMOut):
    id: str
    name: str
    phone: str


class ProducerOut(ORMOut):
    id: str
    name: str
    state: str


class ObligationOut(ORMOut):
    id: str
    producer_id: str
    category: str
    compliance_period: str
    target_kg: float
    fulfilled_kg: float


class CollectionOut(ORMOut):
    id: str
    picker_id: str
    facility_id: str
    item_state: str
    category: str
    serial_or_imei: Optional[str] = None
    declared_weight_kg: float
    weighbridge_weight_kg: Optional[float] = None
    collection_state: str
    facility_state: str
    inter_state: bool
    image_hash: str
    intake_at: datetime
    status: str


class EvidenceAssessmentOut(ORMOut):
    id: str
    collection_id: str
    mode: str
    component_scores: dict
    gates: dict
    score: Optional[float] = None
    decision: str
    reason: str
    weight_source: Optional[str] = None


class CompletionOut(ORMOut):
    id: str
    collection_id: str
    evidence_type: Optional[str] = None
    submitted_at: Optional[datetime] = None
    invoice_weight_kg: Optional[float] = None
    invoice_buyer_id: Optional[str] = None
    facility_revalidated: bool
    manifest_present: bool
    passed: bool
    failure_reasons: list


class NarrationOut(ORMOut):
    id: str
    collection_id: str
    hard_gates: dict
    soft_scores: dict
    score: Optional[float] = None
    decision: str
    reason: str
    corpus_version: str
    sanitizer_passed: bool
    badge_id: Optional[str] = None


class TrustBadgeOut(ORMOut):
    id: str
    collection_id: str
    facility_id: str
    category: str
    weight_kg: float
    evidence_score: Optional[float] = None
    narration_score: Optional[float] = None
    status: str
    issued_at: datetime
    revoked_at: Optional[datetime] = None
    revocation_reason: Optional[str] = None


class BadgeReferenceOut(ORMOut):
    id: str
    badge_id: str
    producer_id: str
    obligation_id: str
    referenced_at: datetime
    weight_kg_applied: float


class MarketplaceBadgeOut(BaseModel):
    id: str
    collection_id: str
    facility_id: str
    facility_state: str
    category: str
    weight_kg: float
    evidence_score: Optional[float] = None
    narration_score: Optional[float] = None
    status: str
    issued_at: datetime
