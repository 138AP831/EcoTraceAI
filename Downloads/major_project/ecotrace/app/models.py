"""SQLAlchemy 2.0 typed declarative models for EcoTrace AI.

All datetimes naive UTC. Enums stored as strings (StrEnum). String UUID PKs.
Postgres-compatible types only (no SQLite-only types).
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# --- Enums (stored as strings) ---
class ItemState(enum.StrEnum):
    intact = "intact"
    dismantled = "dismantled"


class CollectionStatus(enum.StrEnum):
    submitted = "submitted"
    evidence_rejected = "evidence_rejected"
    evidence_hitl = "evidence_hitl"
    evidence_verified = "evidence_verified"
    completion_hold = "completion_hold"
    completion_passed = "completion_passed"
    narration_hitl = "narration_hitl"
    narration_rejected = "narration_rejected"
    badge_issued = "badge_issued"


class BadgeStatus(enum.StrEnum):
    unconsumed = "unconsumed"
    consumed = "consumed"
    revoked = "revoked"


class Decision(enum.StrEnum):
    auto_verified = "auto_verified"
    hitl = "hitl"
    rejected = "rejected"


class NarrationDecision(enum.StrEnum):
    auto_issued = "auto_issued"
    hitl = "hitl"
    rejected = "rejected"


class CompletionEvidenceType(enum.StrEnum):
    destruction_media = "destruction_media"
    sales_invoice = "sales_invoice"
    both = "both"


class WasteCategory(enum.StrEnum):
    IT_telecom = "IT_telecom"
    consumer_electronics = "consumer_electronics"
    large_appliances = "large_appliances"
    small_appliances = "small_appliances"
    lighting = "lighting"
    other = "other"


class RegistrationStatus(enum.StrEnum):
    active = "active"
    expired = "expired"
    revoked = "revoked"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class Picker(TimestampMixin, Base):
    __tablename__ = "pickers"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str] = mapped_column(String, unique=True, nullable=False)


class Facility(TimestampMixin, Base):
    __tablename__ = "facilities"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    registration_no: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    authority: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    registration_status: Mapped[str] = mapped_column(String, nullable=False)
    registration_valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    geofence_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    geofence_lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    geofence_radius_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    authorized_categories: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    daily_capacity_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    booked_capacity_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Producer(TimestampMixin, Base):
    __tablename__ = "producers"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)


class ObligationRecord(TimestampMixin, Base):
    __tablename__ = "obligations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    producer_id: Mapped[str] = mapped_column(String, ForeignKey("producers.id"), nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    compliance_period: Mapped[str] = mapped_column(String, nullable=False)
    target_kg: Mapped[float] = mapped_column(Float, nullable=False)
    fulfilled_kg: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "producer_id", "category", "compliance_period", name="uq_obligation_period"
        ),
    )


class Collection(TimestampMixin, Base):
    __tablename__ = "collections"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    picker_id: Mapped[str] = mapped_column(String, ForeignKey("pickers.id"), nullable=False)
    facility_id: Mapped[str] = mapped_column(String, ForeignKey("facilities.id"), nullable=False)
    item_state: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    serial_or_imei: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    declared_weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    weighbridge_weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    collection_state: Mapped[str] = mapped_column(String, nullable=False)
    facility_state: Mapped[str] = mapped_column(String, nullable=False)
    inter_state: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    image_hash: Mapped[str] = mapped_column(String, nullable=False)
    intake_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String, nullable=False, default="submitted")


class EvidenceAssessment(TimestampMixin, Base):
    __tablename__ = "evidence_assessments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    collection_id: Mapped[str] = mapped_column(String, ForeignKey("collections.id"), nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    component_scores: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    gates: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    weight_source: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class CompletionRecord(TimestampMixin, Base):
    __tablename__ = "completion_records"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    collection_id: Mapped[str] = mapped_column(String, ForeignKey("collections.id"), nullable=False)
    evidence_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    invoice_weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    invoice_buyer_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    facility_revalidated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manifest_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_reasons: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class NarrationAssessment(TimestampMixin, Base):
    __tablename__ = "narration_assessments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    collection_id: Mapped[str] = mapped_column(String, ForeignKey("collections.id"), nullable=False)
    hard_gates: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    soft_scores: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    corpus_version: Mapped[str] = mapped_column(String, nullable=False)
    sanitizer_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TrustBadge(TimestampMixin, Base):
    __tablename__ = "badges"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    collection_id: Mapped[str] = mapped_column(String, ForeignKey("collections.id"), nullable=False, unique=True)
    facility_id: Mapped[str] = mapped_column(String, ForeignKey("facilities.id"), nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    narration_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="unconsumed")
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class BadgeReference(TimestampMixin, Base):
    __tablename__ = "badge_references"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    badge_id: Mapped[str] = mapped_column(String, ForeignKey("badges.id"), nullable=False, unique=True)
    producer_id: Mapped[str] = mapped_column(String, ForeignKey("producers.id"), nullable=False)
    obligation_id: Mapped[str] = mapped_column(String, ForeignKey("obligations.id"), nullable=False)
    referenced_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    weight_kg_applied: Mapped[float] = mapped_column(Float, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
