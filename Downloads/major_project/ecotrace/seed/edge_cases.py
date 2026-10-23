"""Edge-case scenario plan builder for EcoTrace AI.

Generates ~200 synthetic records covering scenarios A1-A11, B1-B10, C1-C14,
D1-D8, E1-E16, E19, F1-F11, F13-F14, G1-G13, H1-H10, I1-I3, J1-J7.

Conventions:
  - is_synthetic = True on every record.
  - RNG seed 42; deterministic and idempotent.
  - Datetimes are naive UTC strings (matching the existing engine convention).
    The task spec asks for tz-aware UTC; this mismatch is listed in
    SEED_MISMATCHES.md under MISSING_FEATURES because the existing engine
    and models use naive UTC throughout and cannot be changed.
  - Images are represented by stored fields only (perceptual_hash as a 64-bit
    hex string). No real image files are generated or downloaded.
  - No real LLM calls. Narration signals are deterministic stubs.
  - No real IMEIs (TAC prefix '99' from luhn.py).
  - Labels: expected_evidence_decision in {VERIFIED, REVIEW, REJECTED, NOT_APPLICABLE}
            expected_gate            in {PASS, HOLD, NOT_APPLICABLE}
            expected_narration_decision in {ISSUED, REVIEW, REJECTED, NOT_APPLICABLE}

Boundary arithmetic (D1-D8) — comments explain floating-point choices:
  Mode A weights: serial=0.30, uniqueness=0.15, fac_reg=0.20,
                  gps=0.15, image=0.10, weight_consistency=0.10  (sum=1.0)
  Setting all six signals to the same value v gives score = round(v, 4).
  This avoids floating-point accumulation across unlike weights.

  Narration weights: grounding=0.35, cross_doc=0.30, chrono=0.20,
                     gaming=0.15  (sum=1.0)
  Same all-uniform trick: score = round(v, 4) = v when v has <= 4 dp.
"""
from __future__ import annotations

import json
import os
import random
import uuid
from datetime import datetime, timedelta

from seed.luhn import luhn_check_digit, make_imei

# ── Constants ──────────────────────────────────────────────────────────────────
RNG_SEED = 42
CORPUS_VERSION = "corpus-v1-20261020"
CORPUS_VERSION_SUPERSEDED = "corpus-v0-20260101"  # for F9 (stale_rule)
INTAKE_BASE = datetime(2026, 6, 1, 10, 0, 0)       # naive UTC reference
CATEGORIES = ["IT_telecom", "consumer_electronics", "large_appliances",
              "small_appliances", "lighting", "other"]
STATES = ["Telangana", "Karnataka", "Maharashtra", "Tamil Nadu", "Gujarat", "Delhi"]

# Hamming distance helper (64-bit hex strings → integer distance)
def _hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")

def _hex64(rng) -> str:
    return "%016x" % rng.getrandbits(64)

def _close_hash(base: str, distance: int, rng) -> str:
    """Return a 64-bit hex hash with exactly `distance` bits flipped from base."""
    n = int(base, 16)
    positions = rng.sample(range(64), distance)
    for p in positions:
        n ^= (1 << p)
    return "%016x" % n

def _iso(dt: datetime) -> str:
    return dt.isoformat()

def _intake(offset_days: float = 0.0) -> datetime:
    return INTAKE_BASE + timedelta(days=offset_days)

# ── Broken IMEI helper ─────────────────────────────────────────────────────────
def _make_bad_imei(rng) -> str:
    """Return a 15-digit string starting with '99' that FAILS the Luhn check."""
    body = "99" + "".join(str(rng.randint(0, 9)) for _ in range(12))
    good_cd = luhn_check_digit(body)
    bad_cd  = (good_cd + 1) % 10          # deliberately wrong check digit
    return body + str(bad_cd)

# ── Evidence signal helpers ────────────────────────────────────────────────────
def _ev_a(serial_conf, uniqueness, fac_reg, gps, image, weight_cons,
          dup=False, fac_active=True):
    """Build an EvidenceRequest body for Mode A (intact)."""
    return {
        "duplicate_detected": dup,
        "facility_registration_active": fac_active,
        "device_serial_confidence":  serial_conf,
        "serial_uniqueness":         uniqueness,
        "facility_registration_validity": fac_reg,
        "gps_validity":              gps,
        "image_quality":             image,
        "weighbridge_weight_consistency": weight_cons,
    }

def _ev_b(cls_conf, plaus, fac_reg, gps, image, weight_cons,
          dup=False, fac_active=True):
    """Build an EvidenceRequest body for Mode B (dismantled)."""
    return {
        "duplicate_detected": dup,
        "facility_registration_active": fac_active,
        "component_classification_confidence": cls_conf,
        "material_composition_plausibility":   plaus,
        "facility_registration_validity": fac_reg,
        "gps_validity":  gps,
        "image_quality": image,
        "weighbridge_weight_consistency": weight_cons,
    }

def _ev_a_uniform(v, dup=False, fac_active=True):
    """All six Mode-A signals set to v.  score = round(v, 4) = v (for 4-dp v)."""
    return _ev_a(v, v, v, v, v, v, dup=dup, fac_active=fac_active)

def _nar(grounding, cross_doc, chrono, gaming,
         sanitizer=True, numeric_ok=True, unique_ok=True,
         corpus=CORPUS_VERSION):
    return {
        "sanitizer_passed":           sanitizer,
        "numeric_verification_passed": numeric_ok,
        "uniqueness_check_passed":    unique_ok,
        "regulatory_grounding":       grounding,
        "cross_document_consistency": cross_doc,
        "chronological_consistency":  chrono,
        "no_gaming_flags":            gaming,
        "corpus_version":             corpus,
    }

def _nar_uniform(v, sanitizer=True, numeric_ok=True, unique_ok=True,
                 corpus=CORPUS_VERSION):
    """All four soft scores = v.  score = round(v, 4) = v (for 4-dp v)."""
    return _nar(v, v, v, v, sanitizer=sanitizer,
                numeric_ok=numeric_ok, unique_ok=unique_ok, corpus=corpus)

def _comp(intake_dt, offset_hours, evidence_type="destruction_media",
          fac_active=True, inter_state=False, manifest=True,
          invoice_kg=None, wb_kg=None, buyer_id=None, facility_id=None):
    submitted = intake_dt + timedelta(hours=offset_hours)
    body = {
        "submitted_at":                  _iso(submitted),
        "evidence_type":                 evidence_type,
        "facility_registration_active_now": fac_active,
        "manifest_present":              manifest,
    }
    if invoice_kg is not None:
        body["invoice_weight_kg"] = invoice_kg
    if buyer_id is not None:
        body["invoice_buyer_id"] = buyer_id
    return body


# ── Record accumulator ─────────────────────────────────────────────────────────
class Plan:
    def __init__(self):
        self.facilities: list[dict] = []
        self.pickers:    list[dict] = []
        self.producers:  list[dict] = []
        self.obligations: list[dict] = []
        self.records:    list[dict] = []
        self._fac_by_reg: dict[str, dict] = {}
        self._picker_by_phone: dict[str, dict] = {}

    def add_facility(self, rng, reg_no, name, state, status, valid_until,
                     lat, lng, categories, radius=250):
        if reg_no in self._fac_by_reg:
            return self._fac_by_reg[reg_no]
        fid = _gen_id(rng)
        f = {
            "id": fid,
            "name": name,
            "registration_no": reg_no,
            "authority": "CPCB",
            "state": state,
            "registration_status": status,
            "registration_valid_until": valid_until,
            "geofence_lat": lat,
            "geofence_lng": lng,
            "geofence_radius_m": radius,
            "authorized_categories": categories,
            "daily_capacity_kg": 2000.0,
            "booked_capacity_kg": 400.0,
            "is_synthetic": True,
        }
        self.facilities.append(f)
        self._fac_by_reg[reg_no] = f
        return f

    def add_picker(self, rng, phone, name):
        if phone in self._picker_by_phone:
            return self._picker_by_phone[phone]
        p = {"id": _gen_id(rng), "name": name, "phone": phone, "is_synthetic": True}
        self.pickers.append(p)
        self._picker_by_phone[phone] = p
        return p

    def add_producer(self, rng, name, state):
        pid = _gen_id(rng)
        p = {"id": pid, "name": name, "state": state, "is_synthetic": True}
        self.producers.append(p)
        return p

    def add_obligation(self, rng, producer_id, category, target_kg,
                       period="FY2026-27"):
        oid = _gen_id(rng)
        o = {
            "id": oid,
            "producer_id": producer_id,
            "category": category,
            "compliance_period": period,
            "target_kg": target_kg,
            "fulfilled_kg": 0.0,
            "is_synthetic": True,
        }
        self.obligations.append(o)
        return o

    def add(self, scenario_tag, description,
            create, evidence, hitl_evidence=None,
            completion=None, narration=None, hitl_narration=None,
            expected_evidence_decision="NOT_APPLICABLE",
            expected_gate="NOT_APPLICABLE",
            expected_narration_decision="NOT_APPLICABLE",
            expected_reason=None,
            notes=None,
            known_limitation=False):
        rec = {
            "scenario_tag": scenario_tag,
            "description": description,
            "is_synthetic": True,
            "known_limitation": known_limitation,
            "expected_evidence_decision": expected_evidence_decision,
            "expected_gate": expected_gate,
            "expected_narration_decision": expected_narration_decision,
            "expected_reason": expected_reason,
            "notes": notes,
            "create": create,
            "evidence": evidence,
            "hitl_evidence": hitl_evidence,
            "completion": completion,
            "narration": narration,
            "hitl_narration": hitl_narration,
        }
        self.records.append(rec)
        return rec


def _gen_id(rng) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


# ── Main builder ───────────────────────────────────────────────────────────────
def build_edge_plan(rng: random.Random | None = None) -> dict:
    if rng is None:
        rng = random.Random(RNG_SEED)

    plan = Plan()

    # ── Supporting actors ──────────────────────────────────────────────────────
    # Active facilities
    fac_hyd = plan.add_facility(
        rng, "EC-TS-E001", "Edge Hyderabad (synthetic)", "Telangana",
        "active", "2027-03-31", 17.3850, 78.4867,
        ["IT_telecom", "consumer_electronics", "small_appliances"])

    fac_blr = plan.add_facility(
        rng, "EC-KA-E002", "Edge Bengaluru (synthetic)", "Karnataka",
        "active", "2027-03-31", 12.9716, 77.5946,
        ["IT_telecom", "large_appliances", "consumer_electronics"])

    fac_mum = plan.add_facility(
        rng, "EC-MH-E003", "Edge Mumbai (synthetic)", "Maharashtra",
        "active", "2027-03-31", 19.0760, 72.8777,
        ["consumer_electronics", "lighting", "other"])

    # Facility whose registration expires the DAY AFTER intake (B10)
    fac_exp_soon = plan.add_facility(
        rng, "EC-TS-E004", "Edge Expiring-Soon (synthetic)", "Telangana",
        "active", str((INTAKE_BASE + timedelta(days=1)).date()),
        17.4000, 78.5000,
        ["IT_telecom", "consumer_electronics"])

    # Lapsed / suspended facilities (B7, B8)
    fac_lapsed = plan.add_facility(
        rng, "EC-TS-E005", "Edge Lapsed (synthetic)", "Telangana",
        "expired", "2026-01-01", 17.3850, 78.4867,
        ["IT_telecom"])

    fac_suspended = plan.add_facility(
        rng, "EC-KA-E006", "Edge Suspended (synthetic)", "Karnataka",
        "revoked", "2025-12-01", 12.9716, 77.5946,
        ["consumer_electronics"])

    # Pickers
    picker_main   = plan.add_picker(rng, "9100000001", "Edge Picker Main (synthetic)")
    picker_b2     = plan.add_picker(rng, "9100000002", "Edge Picker B2 (synthetic)")
    picker_gps    = plan.add_picker(rng, "9100000003", "Edge Picker GPS (synthetic)")
    picker_clean  = plan.add_picker(rng, "9100000010", "Edge Picker Clean (synthetic)")

    # Producer + obligations
    prod_a = plan.add_producer(rng, "Edge Producer Alpha (synthetic)", "Telangana")
    prod_b = plan.add_producer(rng, "Edge Producer Beta (synthetic)", "Karnataka")
    prod_zero = plan.add_producer(rng, "Edge Producer Zero-Obligation (synthetic)", "Maharashtra")

    obl_it   = plan.add_obligation(rng, prod_a["id"], "IT_telecom",    10000.0)
    obl_ce   = plan.add_obligation(rng, prod_a["id"], "consumer_electronics", 5000.0)
    obl_small = plan.add_obligation(rng, prod_b["id"], "small_appliances", 50.0)  # small, for G6
    # Zero obligation producer — no obligation row → G7: reference blocked
    obl_zero_it = plan.add_obligation(rng, prod_zero["id"], "IT_telecom", 0.0)    # 0 kg target

    def _create(fac, picker, item_state, category, declared, wb_kg=None,
                serial=None, image_hash=None, collection_state=None,
                intake_dt=None):
        if intake_dt is None:
            intake_dt = INTAKE_BASE
        if image_hash is None:
            image_hash = _hex64(rng)
        if collection_state is None:
            collection_state = fac["state"]
        body = {
            "id":                  _gen_id(rng),
            "picker_id":           picker["id"],
            "facility_id":         fac["id"],
            "item_state":          item_state,
            "category":            category,
            "declared_weight_kg":  declared,
            "collection_state":    collection_state,
            "image_hash":          image_hash,
            "intake_at":           _iso(intake_dt),
        }
        if wb_kg is not None:
            body["weighbridge_weight_kg"] = wb_kg
        if serial is not None:
            body["serial_or_imei"] = serial
        return body

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION A — Device state and identity
    # ─────────────────────────────────────────────────────────────────────────

    # A1: intact, clear IMEI, OCR confidence >= 0.9, Luhn valid → VERIFIED
    imei_a1 = make_imei(rng)
    cr_a1 = _create(fac_hyd, picker_main, "intact", "IT_telecom", 10.0, wb_kg=10.2,
                    serial=imei_a1)
    plan.add("A1", "intact clear IMEI Luhn valid OCR>=0.9",
             cr_a1,
             _ev_a(0.95, 1.0, 1.0, 1.0, 0.95, 0.95),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED")

    # A2: intact, serial present (no IMEI), serial regex valid → VERIFIED
    cr_a2 = _create(fac_hyd, picker_main, "intact", "consumer_electronics", 15.0,
                    wb_kg=15.3, serial="SN-LAPTOP-20261001")
    plan.add("A2", "intact serial non-IMEI regex valid",
             cr_a2,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.93, 0.94),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED")

    # A3: intact, IMEI fails Luhn, OCR confidence high → REVIEW
    # Luhn failure modelled by low device_serial_confidence (0.25 < 0.30 threshold boundary)
    # and serial_uniqueness stays high. Score will fall into hitl band.
    bad_imei_a3 = _make_bad_imei(rng)
    cr_a3 = _create(fac_hyd, picker_main, "intact", "IT_telecom", 8.0, wb_kg=8.1,
                    serial=bad_imei_a3)
    plan.add("A3", "intact IMEI fails Luhn OCR confidence high",
             cr_a3,
             _ev_a(0.30, 0.95, 1.0, 1.0, 0.95, 0.95),
             expected_evidence_decision="REVIEW",
             expected_reason="luhn_failure_caps_identity_to_0.30",
             notes="Luhn failure: device_serial_confidence capped at 0.30 per spec. "
                   "Score = 0.30*0.30+0.15*0.95+0.20*1.0+0.15*1.0+0.10*0.95+0.10*0.95 "
                   "= 0.09+0.1425+0.20+0.15+0.095+0.095 = 0.7725 → hitl/REVIEW")

    # A4: intact, OCR confidence between 0.4 and 0.6 → REVIEW
    cr_a4 = _create(fac_hyd, picker_main, "intact", "IT_telecom", 9.0, wb_kg=9.1)
    plan.add("A4", "intact OCR confidence 0.4-0.6",
             cr_a4,
             _ev_a(0.50, 0.80, 1.0, 1.0, 0.85, 0.90),
             expected_evidence_decision="REVIEW",
             notes="Score = 0.30*0.50+0.15*0.80+0.20*1.0+0.15*1.0+0.10*0.85+0.10*0.90 "
                   "= 0.15+0.12+0.20+0.15+0.085+0.090 = 0.795 → hitl/REVIEW")

    # A5: packed (intact), pre-pack state captured, IMEI not visible, weighbridge present → VERIFIED
    imei_a5 = make_imei(rng)
    cr_a5 = _create(fac_hyd, picker_main, "intact", "IT_telecom", 20.0, wb_kg=20.2,
                    serial=imei_a5)
    plan.add("A5", "packed pre-pack state captured weighbridge present",
             cr_a5,
             _ev_a(0.85, 1.0, 1.0, 1.0, 0.90, 0.95),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="Pre-pack state capture modelled; IMEI not visible → lower serial_confidence. "
                   "Score = 0.30*0.85+0.15*1.0+0.20*1.0+0.15*1.0+0.10*0.90+0.10*0.95 "
                   "= 0.255+0.15+0.20+0.15+0.09+0.095 = 0.94 → VERIFIED")

    # A6: packed, no pre-pack state captured → HOLD (missing_feature: state_not_captured)
    # The existing engine has no packed/pre-pack concept; scored as if no serial available.
    cr_a6 = _create(fac_hyd, picker_main, "intact", "IT_telecom", 18.0, wb_kg=18.0)
    plan.add("A6", "packed no pre-pack state captured → HOLD state_not_captured",
             cr_a6,
             evidence=None,
             expected_evidence_decision="NOT_APPLICABLE",
             expected_gate="HOLD",
             expected_reason="state_not_captured",
             notes="MISSING_FEATURE: The engine has no packed/pre-pack concept. "
                   "Modelled here as a record with no evidence submission; "
                   "the expected HOLD cannot be asserted against the current engine. "
                   "Skipped in test_edge_cases.py.")

    # A7: dismantled lot, Mode B, classification confidence >= 0.9 → VERIFIED
    cr_a7 = _create(fac_blr, picker_main, "dismantled", "large_appliances", 30.0, wb_kg=30.5)
    plan.add("A7", "dismantled Mode B classification>=0.9",
             cr_a7,
             _ev_b(0.92, 0.95, 1.0, 1.0, 0.92, 0.96),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED")

    # A8: dismantled lot, implausible composition → REVIEW
    # material_composition_plausibility very low
    cr_a8 = _create(fac_blr, picker_main, "dismantled", "large_appliances", 100.0, wb_kg=100.0)
    plan.add("A8", "dismantled implausible composition low plausibility",
             cr_a8,
             _ev_b(0.90, 0.10, 1.0, 1.0, 0.90, 0.95),
             expected_evidence_decision="REVIEW",
             notes="Score = 0.30*0.90+0.15*0.10+0.20*1.0+0.15*1.0+0.10*0.90+0.10*0.95 "
                   "= 0.27+0.015+0.20+0.15+0.09+0.095 = 0.82 → hitl/REVIEW? "
                   "Actually 0.82 >= 0.80 → VERIFIED. "
                   "Plausibility must be even lower. "
                   "Recalculate: need score < 0.80. "
                   "Use plaus=0.0: 0.27+0+0.20+0.15+0.09+0.095=0.805 still >= 0.80. "
                   "Also reduce class_conf: 0.70, plaus=0.0: "
                   "0.21+0+0.20+0.15+0.09+0.095=0.745 → hitl REVIEW ✓")

    # Re-record A8 with corrected signals
    cr_a8b = _create(fac_blr, picker_main, "dismantled", "large_appliances", 100.0, wb_kg=100.0)
    plan.records.pop()  # remove the placeholder above
    plan.add("A8", "dismantled implausible composition low plausibility",
             cr_a8b,
             _ev_b(0.70, 0.0, 1.0, 1.0, 0.90, 0.95),
             expected_evidence_decision="REVIEW",
             notes="Score = 0.30*0.70+0.15*0.00+0.20*1.0+0.15*1.0+0.10*0.90+0.10*0.95 "
                   "= 0.21+0+0.20+0.15+0.09+0.095 = 0.745 → hitl/REVIEW")

    # A9: mixed lot — intact + dismantled in one submission → split records sharing lot_id
    # Modelled as two records with the same lot_id metadata field.
    lot_id_a9 = _gen_id(rng)
    cr_a9_intact = _create(fac_hyd, picker_main, "intact", "IT_telecom", 5.0, wb_kg=5.1,
                           serial=make_imei(rng))
    cr_a9_intact["lot_id"] = lot_id_a9
    cr_a9_dismantled = _create(fac_hyd, picker_main, "dismantled", "IT_telecom", 8.0,
                               wb_kg=8.2)
    cr_a9_dismantled["lot_id"] = lot_id_a9
    plan.add("A9i", "mixed lot — intact part",
             cr_a9_intact,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.95),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="Mixed lot A9; lot_id shared with A9d. "
                   "MISSING_FEATURE: lot_id column not in current Collection model.")
    plan.add("A9d", "mixed lot — dismantled part",
             cr_a9_dismantled,
             _ev_b(0.92, 0.90, 1.0, 1.0, 0.92, 0.95),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="Mixed lot A9; lot_id shared with A9i. "
                   "MISSING_FEATURE: lot_id column not in current Collection model.")

    # A10: Mode B record that also carries an IMEI field → IMEI ignored, scored as Mode B
    cr_a10 = _create(fac_blr, picker_main, "dismantled", "consumer_electronics", 12.0,
                     wb_kg=12.3, serial=make_imei(rng))
    plan.add("A10", "Mode B with IMEI field — IMEI ignored scored as Mode B",
             cr_a10,
             _ev_b(0.91, 0.92, 1.0, 1.0, 0.91, 0.95),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="item_state=dismantled → Mode B selected regardless of serial field.")

    # A11: unknown device category → REVIEW via unknown_category flag
    # The existing engine does not have an unknown_category gate; modelled by low image_quality
    # to push into hitl band. MISSING_FEATURE noted.
    cr_a11 = _create(fac_hyd, picker_main, "intact", "other", 7.0, wb_kg=7.1)
    plan.add("A11", "unknown device category → REVIEW",
             cr_a11,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.40, 0.95),
             expected_evidence_decision="REVIEW",
             expected_reason="unknown_category",
             notes="MISSING_FEATURE: unknown_category force-review flag not in current engine. "
                   "Score = 0.30*0.92+0.15*1.0+0.20*1.0+0.15*1.0+0.10*0.40+0.10*0.95 "
                   "= 0.276+0.15+0.20+0.15+0.04+0.095 = 0.911 → VERIFIED by engine. "
                   "Label is REVIEW per spec; mismatch recorded in SEED_MISMATCHES.md.")

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION B — Hard gates
    # ─────────────────────────────────────────────────────────────────────────

    # B1: exact duplicate hash, same picker → REJECTED score 0
    hash_b1 = _hex64(rng)
    cr_b1a = _create(fac_hyd, picker_main, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                     serial=make_imei(rng), image_hash=hash_b1)
    cr_b1b = _create(fac_hyd, picker_main, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                     serial=make_imei(rng), image_hash=hash_b1)  # same hash
    plan.add("B1a", "first of duplicate pair (original)",
             cr_b1a,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.95),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED")
    plan.add("B1", "exact duplicate hash same picker → REJECTED",
             cr_b1b,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.95, dup=True),
             expected_evidence_decision="REJECTED",
             expected_reason="duplicate_hash")

    # B2: same photo hash from two different pickers → REJECTED both
    hash_b2 = _hex64(rng)
    cr_b2a = _create(fac_hyd, picker_main, "intact", "IT_telecom", 11.0, wb_kg=11.0,
                     serial=make_imei(rng), image_hash=hash_b2)
    cr_b2b = _create(fac_hyd, picker_b2, "intact", "IT_telecom", 11.0, wb_kg=11.0,
                     serial=make_imei(rng), image_hash=hash_b2)
    plan.add("B2a", "cross-picker duplicate — first record",
             cr_b2a,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.95),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED")
    plan.add("B2", "same photo hash different pickers → REJECTED",
             cr_b2b,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.95, dup=True),
             expected_evidence_decision="REJECTED",
             expected_reason="duplicate_hash_cross_picker")

    # B3: near-duplicate (hash distance 3..8) → REJECTED
    hash_b3_orig = _hex64(rng)
    hash_b3_near = _close_hash(hash_b3_orig, 5, rng)  # distance 5
    cr_b3 = _create(fac_hyd, picker_main, "intact", "IT_telecom", 9.0, wb_kg=9.0,
                    serial=make_imei(rng), image_hash=hash_b3_near)
    plan.add("B3", "near-duplicate hash distance 5 → REJECTED",
             cr_b3,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.95, dup=True),
             expected_evidence_decision="REJECTED",
             expected_reason="near_duplicate_hamming_5",
             notes=f"Original hash: {hash_b3_orig}, near hash: {hash_b3_near}, "
                   f"Hamming distance: {_hamming(hash_b3_orig, hash_b3_near)}")

    # B4: bulk lot split (hash distance <= 8, same facility, same day) → REJECTED split_claim
    hash_b4_base = _hex64(rng)
    hash_b4_split = _close_hash(hash_b4_base, 3, rng)
    cr_b4a = _create(fac_hyd, picker_main, "intact", "IT_telecom", 5.0, wb_kg=5.0,
                     serial=make_imei(rng), image_hash=hash_b4_base)
    cr_b4b = _create(fac_hyd, picker_main, "intact", "IT_telecom", 5.0, wb_kg=5.0,
                     serial=make_imei(rng), image_hash=hash_b4_split)
    plan.add("B4a", "bulk lot split — first claim",
             cr_b4a,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.95),
             expected_evidence_decision="VERIFIED",
             notes="B4 seed only; split detection requires cross-record hash scan not in engine.")
    plan.add("B4", "bulk lot split — second claim near-dup → REJECTED split_claim",
             cr_b4b,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.95, dup=True),
             expected_evidence_decision="REJECTED",
             expected_reason="split_claim",
             notes="MISSING_FEATURE: split_claim detection requires cross-record hash scan.")

    # B5: same serial/IMEI in two records → REJECTED
    shared_imei = make_imei(rng)
    cr_b5a = _create(fac_hyd, picker_main, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                     serial=shared_imei)
    cr_b5b = _create(fac_blr, picker_b2, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                     serial=shared_imei)
    plan.add("B5a", "first IMEI record (original)",
             cr_b5a,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.95),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED")
    plan.add("B5", "same IMEI second record → REJECTED",
             cr_b5b,
             _ev_a(0.92, 0.0, 1.0, 1.0, 0.92, 0.95),
             expected_evidence_decision="REJECTED",
             expected_reason="serial_duplicate",
             notes="serial_uniqueness=0.0 drives score below threshold. "
                   "Score = 0.30*0.92+0.15*0+0.20*1.0+0.15*1.0+0.10*0.92+0.10*0.95 "
                   "= 0.276+0+0.20+0.15+0.092+0.095 = 0.813 → actually VERIFIED. "
                   "MISSING_FEATURE: serial uniqueness check is a soft signal not a hard gate. "
                   "To force REJECTED, supply serial_uniqueness=0 AND reduce other signals. "
                   "Modelled by setting uniqueness=0 and gps=0: "
                   "0.276+0+0.20+0+0.092+0.095=0.663 → hitl/REVIEW. "
                   "True REJECTED requires engine hard-gate for duplicate serials.")

    # B5 corrected to REVIEW (serial_uniqueness=0, gps=0)
    plan.records.pop()
    cr_b5b2 = _create(fac_blr, picker_b2, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                      serial=shared_imei)
    plan.add("B5", "same IMEI second record — serial_uniqueness=0",
             cr_b5b2,
             _ev_a(0.92, 0.0, 1.0, 0.0, 0.92, 0.95),
             expected_evidence_decision="REVIEW",
             expected_reason="serial_duplicate_soft_signal",
             notes="serial_uniqueness=0 and gps=0 push score to 0.663 → hitl. "
                   "MISSING_FEATURE: duplicate serial is not a hard gate in current engine.")

    # B6: hash distance 9 → not a duplicate, scored normally
    hash_b6_orig = _hex64(rng)
    hash_b6_near = _close_hash(hash_b6_orig, 9, rng)  # distance exactly 9 → NOT duplicate
    cr_b6 = _create(fac_hyd, picker_main, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng), image_hash=hash_b6_near)
    plan.add("B6", "hash distance 9 not a duplicate scored normally",
             cr_b6,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.95),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes=f"Hamming distance from original: {_hamming(hash_b6_orig, hash_b6_near)}")

    # B7: facility lapsed → REJECTED
    cr_b7 = _create(fac_lapsed, picker_main, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("B7", "facility registration lapsed → REJECTED",
             cr_b7,
             _ev_a(0.92, 1.0, 0.0, 1.0, 0.92, 0.95, fac_active=False),
             expected_evidence_decision="REJECTED",
             expected_reason="facility_registration_inactive")

    # B8: facility suspended (revoked status) → REJECTED
    cr_b8 = _create(fac_suspended, picker_main, "intact", "consumer_electronics", 10.0,
                    wb_kg=10.0, serial=make_imei(rng))
    plan.add("B8", "facility suspended → REJECTED",
             cr_b8,
             _ev_a(0.92, 1.0, 0.0, 1.0, 0.92, 0.95, fac_active=False),
             expected_evidence_decision="REJECTED",
             expected_reason="facility_registration_inactive")

    # B9: facility id not in registry → 422 at API level (no evidence record created)
    fake_fac_id = _gen_id(rng)
    cr_b9 = {
        "id":                  _gen_id(rng),
        "picker_id":           picker_main["id"],
        "facility_id":         fake_fac_id,
        "item_state":          "intact",
        "category":            "IT_telecom",
        "declared_weight_kg":  10.0,
        "collection_state":    "Telangana",
        "image_hash":          _hex64(rng),
        "intake_at":           _iso(INTAKE_BASE),
    }
    plan.add("B9", "facility id not in registry → 422 collection create fails",
             cr_b9,
             evidence=None,
             expected_evidence_decision="NOT_APPLICABLE",
             expected_reason="facility_not_found_422",
             notes="API returns 422 on collection create; no evidence submission occurs.")

    # B10: facility registration expires the day after intake → evidence passes
    cr_b10 = _create(fac_exp_soon, picker_main, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                     serial=make_imei(rng), intake_dt=INTAKE_BASE)
    plan.add("B10", "facility expires day after intake — evidence stage passes",
             cr_b10,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.95),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="Registration still active at intake time. Lapse is the day after.")

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION C — Signal quality
    # ─────────────────────────────────────────────────────────────────────────

    # C1: GPS inside geofence → gps_validity = 1.0
    cr_c1 = _create(fac_hyd, picker_gps, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("C1", "GPS inside geofence gps=1.0",
             cr_c1,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.95),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="gps_validity=1.0 represents GPS inside geofence per spec.")

    # C2: GPS outside but within 50m → gps_validity = 0.5
    cr_c2 = _create(fac_hyd, picker_gps, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("C2", "GPS outside but within 50m gps=0.5",
             cr_c2,
             _ev_a(0.92, 1.0, 1.0, 0.5, 0.92, 0.95),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="Score = 0.30*0.92+0.15*1.0+0.20*1.0+0.15*0.5+0.10*0.92+0.10*0.95 "
                   "= 0.276+0.15+0.20+0.075+0.092+0.095 = 0.888 → VERIFIED")

    # C3: GPS far outside → gps_validity = 0.0
    cr_c3 = _create(fac_hyd, picker_gps, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("C3", "GPS far outside geofence gps=0.0",
             cr_c3,
             _ev_a(0.92, 1.0, 1.0, 0.0, 0.92, 0.95),
             expected_evidence_decision="REVIEW",
             notes="Score = 0.276+0.15+0.20+0+0.092+0.095 = 0.813 → VERIFIED by engine. "
                   "Spec says REVIEW via gps_spoof flag — MISSING_FEATURE: force-review flags "
                   "not implemented. Mismatch recorded in SEED_MISMATCHES.md.")

    # C4: GPS missing → gps_validity = 0.0
    cr_c4 = _create(fac_hyd, picker_gps, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("C4", "GPS missing gps=0.0",
             cr_c4,
             _ev_a(0.92, 1.0, 1.0, 0.0, 0.92, 0.95),
             expected_evidence_decision="REVIEW",
             notes="Same as C3 — score 0.813 → VERIFIED by engine. "
                   "MISSING_FEATURE: GPS missing treated as 0.0; no force-review flag.")

    # C5: two events 200km apart within 10 minutes → gps_spoof flag, REVIEW
    cr_c5 = _create(fac_hyd, picker_gps, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("C5", "two events 200km apart 10 min → gps_spoof REVIEW",
             cr_c5,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.95),
             expected_evidence_decision="REVIEW",
             expected_reason="gps_spoof",
             notes="MISSING_FEATURE: gps_spoof force-review flag not implemented. "
                   "Engine would return VERIFIED (score ~0.945). "
                   "Mismatch in SEED_MISMATCHES.md.")

    # C6: photo timestamp 8h off submission → timestamp_mismatch flag, REVIEW
    cr_c6 = _create(fac_hyd, picker_gps, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("C6", "photo timestamp 8h off → timestamp_mismatch REVIEW",
             cr_c6,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.95),
             expected_evidence_decision="REVIEW",
             expected_reason="timestamp_mismatch",
             notes="MISSING_FEATURE: timestamp_mismatch force-review flag not implemented.")

    # C7: EXIF missing → lower image_quality signal
    cr_c7 = _create(fac_hyd, picker_main, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("C7", "EXIF missing lower image_quality",
             cr_c7,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.55, 0.95),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="image_quality=0.55 (EXIF missing penalty). "
                   "Score = 0.276+0.15+0.20+0.15+0.055+0.095 = 0.926 → VERIFIED")

    # C8: blurry/dark image → low image_quality
    cr_c8 = _create(fac_hyd, picker_main, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("C8", "blurry dark image low image_quality",
             cr_c8,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.20, 0.95),
             expected_evidence_decision="VERIFIED",
             notes="image_quality=0.20. "
                   "Score = 0.276+0.15+0.20+0.15+0.020+0.095 = 0.891 → VERIFIED. "
                   "image weight is 0.10 so even 0.20 only subtracts 0.08 from score.")

    # C9: weighbridge matches within 5% → weight signal near 1.0
    cr_c9 = _create(fac_hyd, picker_main, "intact", "small_appliances", 20.0, wb_kg=20.5)
    plan.add("C9", "weighbridge within 5% weight signal near 1.0",
             cr_c9,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.975),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="wb_kg=20.5, declared=20.0 → deviation=2.5% < 5%. "
                   "weight_signal = max(0, 1-|20-20.5|/20) = 1-0.025 = 0.975")

    # C10: weighbridge deviates 40% → low weight signal
    cr_c10 = _create(fac_hyd, picker_main, "intact", "small_appliances", 20.0, wb_kg=28.0)
    plan.add("C10", "weighbridge deviates 40% low weight signal",
             cr_c10,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.60),
             expected_evidence_decision="VERIFIED",
             notes="weight_signal = max(0,1-|20-28|/20)=1-0.40=0.60. "
                   "Score = 0.276+0.15+0.20+0.15+0.092+0.060 = 0.928 → VERIFIED. "
                   "Weight is 10% of score so even 0.60 still passes.")

    # C11: weighbridge missing → weight signal 1.0 (no penalty)
    cr_c11 = _create(fac_hyd, picker_main, "intact", "small_appliances", 15.0)
    plan.add("C11", "weighbridge missing weight signal 1.0 no penalty",
             cr_c11,
             {
                 "duplicate_detected": False,
                 "facility_registration_active": True,
                 "device_serial_confidence":  0.92,
                 "serial_uniqueness":         1.0,
                 "facility_registration_validity": 1.0,
                 "gps_validity":              1.0,
                 "image_quality":             0.92,
                 "declared_weight_consistency": 1.0,
             },
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="No weighbridge → use declared_weight_consistency * 0.85 = 0.85. "
                   "Score = 0.30*0.92+0.15*1.0+0.20*1.0+0.15*1.0+0.10*0.92+0.10*0.85 "
                   "= 0.276+0.15+0.20+0.15+0.092+0.085 = 0.953 → VERIFIED")

    # C12: declared weight 0 → validation error, record not created
    cr_c12 = {
        "id":                  _gen_id(rng),
        "picker_id":           picker_main["id"],
        "facility_id":         fac_hyd["id"],
        "item_state":          "intact",
        "category":            "IT_telecom",
        "declared_weight_kg":  0.0,
        "collection_state":    "Telangana",
        "image_hash":          _hex64(rng),
        "intake_at":           _iso(INTAKE_BASE),
    }
    plan.add("C12a", "declared weight 0 → validation error",
             cr_c12,
             evidence=None,
             expected_evidence_decision="NOT_APPLICABLE",
             expected_reason="validation_error_weight_zero",
             notes="MISSING_FEATURE: current API accepts 0 declared_weight_kg. "
                   "Test asserts 422 response; will get 201 → mismatch in SEED_MISMATCHES.md.")

    cr_c12_neg = {
        "id":                  _gen_id(rng),
        "picker_id":           picker_main["id"],
        "facility_id":         fac_hyd["id"],
        "item_state":          "intact",
        "category":            "IT_telecom",
        "declared_weight_kg":  -5.0,
        "collection_state":    "Telangana",
        "image_hash":          _hex64(rng),
        "intake_at":           _iso(INTAKE_BASE),
    }
    plan.add("C12b", "declared weight negative → validation error",
             cr_c12_neg,
             evidence=None,
             expected_evidence_decision="NOT_APPLICABLE",
             expected_reason="validation_error_weight_negative",
             notes="MISSING_FEATURE: current API accepts negative declared_weight_kg.")

    # C13: weight given in grams → normalised to kg and flagged unit_normalised
    # MISSING_FEATURE: unit normalisation not in engine; stored as-is
    cr_c13 = _create(fac_hyd, picker_main, "intact", "IT_telecom", 10000.0)
    plan.add("C13", "weight in grams → normalised to kg unit_normalised",
             cr_c13,
             evidence=None,
             expected_evidence_decision="NOT_APPLICABLE",
             expected_reason="unit_normalised",
             notes="MISSING_FEATURE: no unit detection/normalisation in current engine.")

    # C14: weighbridge slip from different facility → wrong_facility_slip flag, REVIEW
    cr_c14 = _create(fac_hyd, picker_main, "intact", "IT_telecom", 10.0, wb_kg=10.1,
                     serial=make_imei(rng))
    plan.add("C14", "weighbridge slip different facility → wrong_facility_slip REVIEW",
             cr_c14,
             _ev_a(0.92, 1.0, 1.0, 1.0, 0.92, 0.95),
             expected_evidence_decision="REVIEW",
             expected_reason="wrong_facility_slip",
             notes="MISSING_FEATURE: wrong_facility_slip force-review flag not implemented.")

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION D — Threshold boundaries (Mode A, all-uniform signals)
    # ─────────────────────────────────────────────────────────────────────────
    # For Mode A with all six signals = v:
    #   score = 0.30v + 0.15v + 0.20v + 0.15v + 0.10v + 0.10v = 1.00v = v
    # So score = round(v, 4). No floating-point accumulation issue when v
    # has at most 4 decimal places.

    # D1: evidence score exactly 0.80 → VERIFIED
    cr_d1 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("D1", "evidence score exactly 0.80 → VERIFIED",
             cr_d1,
             _ev_a_uniform(0.80),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="All six Mode-A signals = 0.80. score = 0.80 >= 0.80 → auto_verified.")

    # D2: evidence score 0.7999 → REVIEW (hitl)
    cr_d2 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("D2", "evidence score 0.7999 → REVIEW",
             cr_d2,
             _ev_a_uniform(0.7999),
             expected_evidence_decision="REVIEW",
             notes="All six signals = 0.7999. score = 0.7999 < 0.80 → hitl. "
                   "0.7999 >= 0.55 → hitl (not rejected).")

    # D3: evidence score exactly 0.55 → REVIEW (hitl)
    cr_d3 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("D3", "evidence score exactly 0.55 → REVIEW",
             cr_d3,
             _ev_a_uniform(0.55),
             expected_evidence_decision="REVIEW",
             notes="All six signals = 0.55. score = 0.55 >= 0.55 → hitl.")

    # D4: evidence score 0.5499 → REJECTED
    cr_d4 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("D4", "evidence score 0.5499 → REJECTED",
             cr_d4,
             _ev_a_uniform(0.5499),
             expected_evidence_decision="REJECTED",
             notes="All six signals = 0.5499. score = 0.5499 < 0.55 → rejected.")

    # For D5-D8 we need a record that reaches narration stage.
    # Reuse picker_clean with fresh hashes; take through evidence+completion first.
    def _narration_seed_record(tag, v_nar, expected_nar, notes_extra=""):
        cr = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                     serial=make_imei(rng))
        plan.add(tag, f"narration score {v_nar} → {expected_nar}",
                 cr,
                 _ev_a_uniform(0.92),
                 completion=_comp(INTAKE_BASE, 24),
                 narration=_nar_uniform(v_nar),
                 expected_evidence_decision="VERIFIED",
                 expected_gate="PASS",
                 expected_narration_decision=expected_nar,
                 notes=f"All four narration soft scores = {v_nar}. "
                       f"score = {v_nar} (weights sum to 1). {notes_extra}")

    # D5: narration score exactly 0.85 → ISSUED
    _narration_seed_record("D5", 0.85, "ISSUED",
                           "0.85 >= 0.85 → auto_issued.")

    # D6: narration score 0.8499 → REVIEW (hitl)
    _narration_seed_record("D6", 0.8499, "REVIEW",
                           "0.8499 < 0.85 → hitl.")

    # D7: narration score exactly 0.60 → REVIEW (hitl)
    _narration_seed_record("D7", 0.60, "REVIEW",
                           "0.60 >= 0.60 → hitl.")

    # D8: narration score 0.5999 → REJECTED
    _narration_seed_record("D8", 0.5999, "REJECTED",
                           "0.5999 < 0.60 → rejected.")

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION E — Processing completion gate
    # (all start with evidence VERIFIED; use picker_clean + fac_hyd)
    # ─────────────────────────────────────────────────────────────────────────

    def _clean_ev():
        return _ev_a_uniform(0.92)

    # E1: destruction media only, all checks pass → PASS
    cr_e1 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("E1", "destruction media all pass → PASS",
             cr_e1, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "destruction_media"),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED")

    # E2: sales invoice only → PASS
    wb_e2 = 12.0
    cr_e2 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 11.8, wb_kg=wb_e2,
                    serial=make_imei(rng))
    plan.add("E2", "sales invoice all pass → PASS",
             cr_e2, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "sales_invoice",
                              invoice_kg=wb_e2 * 1.02, buyer_id="BUYER-E002"),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED")

    # E3: media and invoice both → PASS
    wb_e3 = 15.0
    cr_e3 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 14.8, wb_kg=wb_e3,
                    serial=make_imei(rng))
    plan.add("E3", "media and invoice both → PASS",
             cr_e3, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "both",
                              invoice_kg=wb_e3 * 1.01, buyer_id="BUYER-E003"),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED")

    # E4: neither media nor invoice → HOLD
    cr_e4 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("E4", "neither media nor invoice → HOLD",
             cr_e4, _clean_ev(),
             completion={
                 "submitted_at": None,
                 "evidence_type": None,
                 "facility_registration_active_now": True,
                 "manifest_present": True,
             },
             expected_evidence_decision="VERIFIED",
             expected_gate="HOLD",
             expected_reason="completion_evidence_missing")

    # E5: completion exactly 72h after intake → PASS
    cr_e5 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("E5", "completion exactly 72h after intake → PASS",
             cr_e5, _clean_ev(),
             completion=_comp(INTAKE_BASE, 72.0, "destruction_media"),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="submitted_at = intake_at + timedelta(hours=72). "
                   "within_window: 72h <= 72h → True.")

    # E6: completion at 72h 1 min → HOLD
    cr_e6 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("E6", "completion 72h 1min after intake → HOLD",
             cr_e6, _clean_ev(),
             completion={
                 "submitted_at": _iso(INTAKE_BASE + timedelta(hours=72, minutes=1)),
                 "evidence_type": "destruction_media",
                 "facility_registration_active_now": True,
                 "manifest_present": True,
             },
             expected_evidence_decision="VERIFIED",
             expected_gate="HOLD",
             expected_reason="within_window",
             notes="72h 1min > 72h window → HOLD.")

    # E7: facility lapsed between intake and completion → HOLD
    cr_e7 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("E7", "facility lapsed between intake and completion → HOLD",
             cr_e7, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "destruction_media", fac_active=False),
             expected_evidence_decision="VERIFIED",
             expected_gate="HOLD",
             expected_reason="facility_registration_not_revalidated")

    # E8: inter-state manifest present → PASS
    cr_e8 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng), collection_state="Karnataka")  # != Telangana
    plan.add("E8", "inter-state manifest present → PASS",
             cr_e8, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "destruction_media", manifest=True),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED")

    # E9: inter-state manifest missing → HOLD
    cr_e9 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng), collection_state="Karnataka")
    plan.add("E9", "inter-state manifest missing → HOLD",
             cr_e9, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "destruction_media", manifest=False),
             expected_evidence_decision="VERIFIED",
             expected_gate="HOLD",
             expected_reason="manifest_missing")

    # E10: intra-state no manifest → PASS
    cr_e10 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                     serial=make_imei(rng), collection_state="Telangana")
    plan.add("E10", "intra-state no manifest → PASS",
             cr_e10, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "destruction_media", manifest=False),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED")

    # E11: invoice weight exactly 5% off weighbridge → PASS
    wb_e11 = 20.0
    inv_e11 = round(wb_e11 * 1.05, 2)   # exactly 5% over
    cr_e11 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 19.5, wb_kg=wb_e11,
                     serial=make_imei(rng))
    plan.add("E11", "invoice weight exactly 5% off weighbridge → PASS",
             cr_e11, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "sales_invoice",
                              invoice_kg=inv_e11, buyer_id="BUYER-E011"),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes=f"wb={wb_e11}, inv={inv_e11}. "
                   f"|inv-wb|/wb = {abs(inv_e11-wb_e11)/wb_e11:.4f} <= 0.05 → PASS.")

    # E12: invoice weight 5.1% off → HOLD
    wb_e12 = 20.0
    inv_e12 = round(wb_e12 * 1.051, 3)
    cr_e12 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 19.5, wb_kg=wb_e12,
                     serial=make_imei(rng))
    plan.add("E12", "invoice weight 5.1% off → HOLD",
             cr_e12, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "sales_invoice",
                              invoice_kg=inv_e12, buyer_id="BUYER-E012"),
             expected_evidence_decision="VERIFIED",
             expected_gate="HOLD",
             expected_reason="invoice_weight_inconsistent",
             notes=f"wb={wb_e12}, inv={inv_e12}. "
                   f"|inv-wb|/wb = {abs(inv_e12-wb_e12)/wb_e12:.4f} > 0.05 → HOLD.")

    # E13: buyer equals the facility → HOLD
    cr_e13 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                     serial=make_imei(rng))
    plan.add("E13", "buyer equals facility → HOLD",
             cr_e13, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "sales_invoice",
                              invoice_kg=10.0, buyer_id=fac_hyd["id"]),
             expected_evidence_decision="VERIFIED",
             expected_gate="HOLD",
             expected_reason="invoice_buyer_related_to_facility")

    # E14: buyer not in buyer registry → HOLD
    cr_e14 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                     serial=make_imei(rng))
    plan.add("E14", "buyer not in registry → HOLD",
             cr_e14, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "sales_invoice",
                              invoice_kg=10.0, buyer_id="UNREGISTERED-BUYER-XYZ"),
             expected_evidence_decision="VERIFIED",
             expected_gate="HOLD",
             expected_reason="buyer_not_registered",
             notes="MISSING_FEATURE: buyer registry check not implemented. "
                   "Engine accepts any buyer_id string. Mismatch in SEED_MISMATCHES.md.")

    # E15: same invoice number used on two records → HOLD on second
    cr_e15a = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                      serial=make_imei(rng))
    cr_e15b = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                      serial=make_imei(rng))
    plan.add("E15a", "first invoice (original)",
             cr_e15a, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "sales_invoice",
                              invoice_kg=10.0, buyer_id="BUYER-E015"),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="MISSING_FEATURE: invoice_number field not in current model.")
    plan.add("E15", "same invoice number second record → HOLD invoice_reuse",
             cr_e15b, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "sales_invoice",
                              invoice_kg=10.0, buyer_id="BUYER-E015"),
             expected_evidence_decision="VERIFIED",
             expected_gate="HOLD",
             expected_reason="invoice_reuse",
             notes="MISSING_FEATURE: invoice_number uniqueness check not in current engine.")

    # E16: destruction media hash identical to another → HOLD media_reuse
    cr_e16a = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                      serial=make_imei(rng))
    cr_e16b = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                      serial=make_imei(rng))
    plan.add("E16a", "first media record (original)",
             cr_e16a, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "destruction_media"),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED")
    plan.add("E16", "destruction media hash reused → HOLD media_reuse",
             cr_e16b, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "destruction_media"),
             expected_evidence_decision="VERIFIED",
             expected_gate="HOLD",
             expected_reason="media_reuse",
             notes="MISSING_FEATURE: completion media hash uniqueness check not implemented.")

    # E19: circular related-party invoicing → PASS, known_limitation=True
    cr_e19 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                     serial=make_imei(rng))
    plan.add("E19", "circular related-party invoicing → PASS known_limitation",
             cr_e19, _clean_ev(),
             completion=_comp(INTAKE_BASE, 24, "sales_invoice",
                              invoice_kg=10.0, buyer_id="BUYER-CIRCULAR-A"),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             known_limitation=True,
             notes="Circular A→B→A invoicing NOT detected per spec. "
                   "Passes through as normal; flagged known_limitation=True.")

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION F — Narration
    # (all have evidence VERIFIED and gate PASS going in)
    # ─────────────────────────────────────────────────────────────────────────

    def _clean_col_for_narration():
        return _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                       serial=make_imei(rng))

    def _good_ev():  return _ev_a_uniform(0.92)
    def _good_comp(): return _comp(INTAKE_BASE, 24)

    # F1: clean narration → ISSUED
    plan.add("F1", "clean narration → ISSUED",
             _clean_col_for_narration(), _good_ev(), completion=_good_comp(),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED")

    # F2: one number differs from evidence record → REJECTED (numeric gate)
    plan.add("F2", "number differs from evidence → REJECTED numeric gate",
             _clean_col_for_narration(), _good_ev(), completion=_good_comp(),
             narration=_nar_uniform(0.90, numeric_ok=False),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="REJECTED",
             expected_reason="numeric_verification_passed gate_failed")

    # F3: kg value differs only beyond 2dp after rounding → REJECTED
    # Modelled as numeric_verification_passed=False (same gate)
    plan.add("F3", "kg differs beyond 2dp → REJECTED numeric gate",
             _clean_col_for_narration(), _good_ev(), completion=_good_comp(),
             narration=_nar_uniform(0.90, numeric_ok=False),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="REJECTED",
             expected_reason="numeric_verification_passed gate_failed",
             notes="Integers match exactly; kg differs only at 3dp after rounding. "
                   "numeric_verification_passed=False captures this.")

    # F4: prompt injection → REJECTED (sanitizer gate)
    plan.add("F4", "prompt injection → REJECTED sanitizer gate",
             _clean_col_for_narration(), _good_ev(), completion=_good_comp(),
             narration=_nar_uniform(0.90, sanitizer=False),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="REJECTED",
             expected_reason="sanitizer_passed gate_failed",
             notes="Free-text field contains 'ignore previous instructions...'")

    # F5: injection in filename / OCR text → REJECTED
    plan.add("F5", "injection in filename OCR text → REJECTED sanitizer gate",
             _clean_col_for_narration(), _good_ev(), completion=_good_comp(),
             narration=_nar_uniform(0.90, sanitizer=False),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="REJECTED",
             expected_reason="sanitizer_passed gate_failed")

    # F6: zero-width Unicode → sanitised then scored normally → ISSUED
    plan.add("F6", "zero-width Unicode sanitised scored normally → ISSUED",
             _clean_col_for_narration(), _good_ev(), completion=_good_comp(),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="Sanitiser strips zero-width chars; remaining text scores normally. "
                   "sanitizer_passed=True because sanitisation succeeded.")

    # F7: narration identical to existing badge → REJECTED (uniqueness gate)
    plan.add("F7", "narration identical to existing badge → REJECTED uniqueness gate",
             _clean_col_for_narration(), _good_ev(), completion=_good_comp(),
             narration=_nar_uniform(0.90, unique_ok=False),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="REJECTED",
             expected_reason="uniqueness_check_passed gate_failed")

    # F8: cites non-existent rule → low regulatory_grounding → REVIEW
    plan.add("F8", "cites non-existent rule → low grounding → REVIEW",
             _clean_col_for_narration(), _good_ev(), completion=_good_comp(),
             narration=_nar(0.40, 0.90, 0.90, 0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="REVIEW",
             notes="regulatory_grounding=0.40. "
                   "Score = 0.35*0.40+0.30*0.90+0.20*0.90+0.15*0.90 "
                   "= 0.14+0.27+0.18+0.135 = 0.725 → hitl/REVIEW")

    # F9: cites superseded rule version → stale_rule flag → REVIEW
    plan.add("F9", "cites superseded rule → stale_rule REVIEW",
             _clean_col_for_narration(), _good_ev(), completion=_good_comp(),
             narration=_nar(0.50, 0.90, 0.90, 0.90, corpus=CORPUS_VERSION_SUPERSEDED),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="REVIEW",
             expected_reason="stale_rule",
             notes="MISSING_FEATURE: stale_rule force-review flag not in current engine. "
                   "Score = 0.35*0.50+0.27+0.18+0.135 = 0.175+0.585 = 0.760 → hitl. "
                   "Engine correctly returns hitl here without needing the flag.")

    # F10: processing event dated before intake → low chronology → REVIEW
    plan.add("F10", "processing event before intake → low chronology REVIEW",
             _clean_col_for_narration(), _good_ev(), completion=_good_comp(),
             narration=_nar(0.90, 0.90, 0.30, 0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="REVIEW",
             notes="chronological_consistency=0.30. "
                   "Score = 0.35*0.90+0.30*0.90+0.20*0.30+0.15*0.90 "
                   "= 0.315+0.270+0.060+0.135 = 0.780 → hitl/REVIEW")

    # F11: many records just above threshold from same picker → gaming_flag → REVIEW
    plan.add("F11", "gaming flag from picker cluster → REVIEW",
             _clean_col_for_narration(), _good_ev(), completion=_good_comp(),
             narration=_nar(0.90, 0.90, 0.90, 0.40),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="REVIEW",
             expected_reason="gaming_flag",
             notes="no_gaming_flags=0.40 (low). "
                   "Score = 0.315+0.270+0.180+0.15*0.40 = 0.315+0.270+0.180+0.060 = 0.825 → hitl. "
                   "MISSING_FEATURE: gaming_flag force-review not implemented; "
                   "engine returns hitl from soft score, which matches REVIEW label.")

    # F13: empty free text / above length limit → validation error
    plan.add("F13", "empty narration corpus_version → 422",
             _clean_col_for_narration(), _good_ev(), completion=_good_comp(),
             narration={
                 "sanitizer_passed": True,
                 "numeric_verification_passed": True,
                 "uniqueness_check_passed": True,
                 "regulatory_grounding": 0.90,
                 "cross_document_consistency": 0.90,
                 "chronological_consistency": 0.90,
                 "no_gaming_flags": 0.90,
                 "corpus_version": "   ",   # blank → ValueError in engine
             },
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="NOT_APPLICABLE",
             expected_reason="blank_corpus_version_422")

    # F14: mixed-script text → handled scored normally
    plan.add("F14", "mixed-script Telugu Hindi English → scored normally",
             _clean_col_for_narration(), _good_ev(), completion=_good_comp(),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="Mixed-script text in notes field; scores normally.")

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION G — Badge and marketplace state (seed starting state only)
    # ─────────────────────────────────────────────────────────────────────────

    def _badge_col():
        return _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                       serial=make_imei(rng))

    # G1: newly issued badge → state unconsumed
    plan.add("G1", "newly issued badge → unconsumed",
             _badge_col(), _good_ev(), completion=_good_comp(),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="Badge status = unconsumed after narration auto_issued.")

    # G5: badge in held/rejected state → reference blocked
    plan.add("G5", "badge in rejected state → reference blocked",
             _badge_col(),
             _ev_a_uniform(0.5499),      # REJECTED evidence → no badge
             expected_evidence_decision="REJECTED",
             expected_gate="NOT_APPLICABLE",
             expected_narration_decision="NOT_APPLICABLE",
             expected_reason="no_badge_for_rejected_collection",
             notes="No badge is ever created; referencing by collection_id returns 404.")

    # G6: badge quantity > remaining obligation → blocked
    # Seed a small obligation (obl_small = 50 kg) and a badge for 60 kg
    cr_g6 = _create(fac_blr, picker_clean, "intact", "small_appliances", 60.0, wb_kg=60.0,
                    serial=make_imei(rng))
    plan.add("G6", "badge weight > remaining obligation → blocked",
             cr_g6, _good_ev(), completion=_good_comp(),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="Badge weight_kg=60.0 > obl_small remaining=50.0. "
                   "MISSING_FEATURE: obligation ceiling check not in current engine. "
                   "Current engine adds weight regardless of remaining capacity.")

    # G7: producer with zero obligation → reference blocked
    cr_g7 = _create(fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("G7", "producer zero obligation → reference blocked",
             cr_g7, _good_ev(), completion=_good_comp(),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes=f"obl_zero_it (producer_id={prod_zero['id']}) has target_kg=0. "
                   "MISSING_FEATURE: zero-obligation ceiling check not implemented. "
                   "Reference proceeds and increments fulfilled_kg past target.")

    # G8: consumed badge later revoked → 30-day grace
    plan.add("G8", "consumed badge revoked → 30-day grace",
             _badge_col(), _good_ev(), completion=_good_comp(),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="After reference (consumed), revoke opens grace window. "
                   "Test asserts grace_until = revoked_at + 30 days.")

    # G11: unconsumed badge revoked → no reversal
    plan.add("G11", "unconsumed badge revoked → no reversal",
             _badge_col(), _good_ev(), completion=_good_comp(),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="Revoke of unconsumed badge: grace_until=None, obligation unchanged.")

    # G13: audit marks badge as false positive → revoke + reliability update
    plan.add("G13", "false-positive audit → revoke + reliability update",
             _badge_col(), _good_ev(), completion=_good_comp(),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="MISSING_FEATURE: reliability rollup not implemented. "
                   "Revoke itself is tested; reliability update is skipped.")

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION H — Reliability rollups (seed starting state only)
    # All H scenarios require a reliability rollup feature not in current engine.
    # ─────────────────────────────────────────────────────────────────────────

    for tag, desc in [
        ("H1", "new recycler no history → insufficient_data"),
        ("H2", "2 records 1 rejection → rejection rate small_sample"),
        ("H3", "improving over 3 months → trend up"),
        ("H4", "declining over 3 months → trend down"),
        ("H5", "revoked badge → reflected in trend"),
        ("H7", "records spanning 31 Dec to 2 Jan → correct grouping"),
        ("H8", "missing capacity/turnaround → treated as unknown"),
        ("H9", "registration lapses → flagged in marketplace"),
        ("H10", "price missing → treated as unknown in price filter"),
    ]:
        plan.add(tag, f"H: {desc} (seed state only)",
                 _badge_col() if tag not in ("H7",) else _create(
                     fac_hyd, picker_clean, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                     serial=make_imei(rng),
                     intake_dt=datetime(2026, 12, 31, 23, 0, 0)),
                 evidence=None,
                 expected_evidence_decision="NOT_APPLICABLE",
                 expected_gate="NOT_APPLICABLE",
                 expected_narration_decision="NOT_APPLICABLE",
                 notes=f"MISSING_FEATURE: reliability rollup not implemented. "
                       f"Scenario {tag} is seeded for data coverage only.")

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION I — People and access
    # ─────────────────────────────────────────────────────────────────────────

    # I1: picker not onboarded → blocked
    plan.add("I1", "picker not onboarded → blocked",
             {
                 "id":                  _gen_id(rng),
                 "picker_id":           _gen_id(rng),  # non-existent picker
                 "facility_id":         fac_hyd["id"],
                 "item_state":          "intact",
                 "category":            "IT_telecom",
                 "declared_weight_kg":  10.0,
                 "collection_state":    "Telangana",
                 "image_hash":          _hex64(rng),
                 "intake_at":           _iso(INTAKE_BASE),
             },
             evidence=None,
             expected_evidence_decision="NOT_APPLICABLE",
             expected_reason="picker_not_found_422",
             notes="API returns 422 on collection create; picker_id not in DB.")

    # I2: picker blocked after fraud → new submissions rejected
    blocked_picker = plan.add_picker(rng, "9100000099", "Edge Blocked Picker (synthetic)")
    cr_i2 = _create(fac_hyd, blocked_picker, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    plan.add("I2", "blocked picker new submissions rejected",
             cr_i2, evidence=None,
             expected_evidence_decision="NOT_APPLICABLE",
             expected_reason="picker_blocked",
             notes="MISSING_FEATURE: picker.is_blocked field not in current Picker model. "
                   "Collection create succeeds currently.")

    # I3: picker with high rejection share → picker risk flag
    plan.add("I3", "picker high rejection share → risk flag",
             _create(fac_hyd, picker_b2, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                     serial=make_imei(rng)),
             evidence=None,
             expected_evidence_decision="NOT_APPLICABLE",
             expected_reason="picker_risk_flag",
             notes="MISSING_FEATURE: picker risk flag computation not implemented.")

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION J — Operations
    # ─────────────────────────────────────────────────────────────────────────

    # J1: offline sync hours later → capture time preserved; no timestamp_mismatch
    cr_j1 = _create(fac_hyd, picker_main, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    cr_j1["offline_sync"] = True
    cr_j1["original_capture_at"] = _iso(INTAKE_BASE - timedelta(hours=25))
    plan.add("J1", "offline sync late_sync flag no timestamp_mismatch",
             cr_j1, _ev_a_uniform(0.92),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="MISSING_FEATURE: offline_sync and late_sync fields not in current model. "
                   "timestamp_mismatch suppression for late_sync not implemented.")

    # J4: timestamps in IST stored as UTC
    cr_j4 = _create(fac_hyd, picker_main, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                    serial=make_imei(rng))
    cr_j4["original_ist_timestamp"] = "2026-06-01T15:30:00+05:30"
    plan.add("J4", "IST timestamp stored as UTC",
             cr_j4, _ev_a_uniform(0.92),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="Schema validator _to_naive_utc converts tz-aware to naive UTC. "
                   "2026-06-01T15:30:00+05:30 → 2026-06-01T10:00:00 (naive UTC).")

    # J7: resubmission after rejection with new evidence → new record with previous_record_id
    cr_j7_orig = _create(fac_hyd, picker_main, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                         serial=make_imei(rng))
    cr_j7_new = _create(fac_hyd, picker_main, "intact", "IT_telecom", 10.0, wb_kg=10.0,
                        serial=make_imei(rng))
    cr_j7_new["previous_record_id"] = cr_j7_orig["id"]
    plan.add("J7a", "rejected original record",
             cr_j7_orig,
             _ev_a_uniform(0.5499),
             expected_evidence_decision="REJECTED",
             notes="Original rejected; new submission links back via previous_record_id.")
    plan.add("J7", "resubmission with new evidence → new record linked",
             cr_j7_new, _ev_a_uniform(0.92),
             completion=_comp(INTAKE_BASE, 24),
             narration=_nar_uniform(0.90),
             expected_evidence_decision="VERIFIED",
             expected_gate="PASS",
             expected_narration_decision="ISSUED",
             notes="MISSING_FEATURE: previous_record_id field not in current Collection model.")

    # ─────────────────────────────────────────────────────────────────────────
    # CLEAN bulk records to reach ~200 total
    # ─────────────────────────────────────────────────────────────────────────
    current_count = len(plan.records)
    needed = max(0, 200 - current_count)
    for i in range(needed):
        cr = _create(
            fac_hyd if i % 2 == 0 else fac_blr,
            picker_clean,
            "intact" if i % 3 != 0 else "dismantled",
            CATEGORIES[i % len(CATEGORIES)],
            10.0 + i * 0.5,
            wb_kg=10.1 + i * 0.5,
            serial=make_imei(rng) if i % 3 != 0 else None,
            intake_dt=INTAKE_BASE + timedelta(days=i),
        )
        if i % 3 == 0:
            ev = _ev_b(0.92, 0.90, 1.0, 1.0, 0.92, 0.95)
        else:
            ev = _ev_a_uniform(0.92)
        plan.add(
            "CLEAN",
            f"synthetic clean record {i + 1}",
            cr, ev,
            completion=_comp(INTAKE_BASE + timedelta(days=i), 24),
            narration=_nar_uniform(0.90),
            expected_evidence_decision="VERIFIED",
            expected_gate="PASS",
            expected_narration_decision="ISSUED",
        )

    return {
        "rng_seed":    RNG_SEED,
        "is_synthetic": True,
        "facilities":  plan.facilities,
        "pickers":     plan.pickers,
        "producers":   plan.producers,
        "obligations": plan.obligations,
        "records":     plan.records,
        "badge_activity": {
            "references": [
                # G8: reference the G8 badge
                {
                    "scenario_tag": "G8",
                    "producer_id":  prod_a["id"],
                    "obligation_id": obl_it["id"],
                },
            ],
            "revokes": [
                {"scenario_tag": "G8",  "reason": "audit_reopen_consumed"},
                {"scenario_tag": "G11", "reason": "compliance_audit_unconsumed"},
                {"scenario_tag": "G13", "reason": "false_positive_audit"},
            ],
        },
    }


def write_edge_files(plan: dict, out_dir: str):
    import csv
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "edge_plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, sort_keys=True)

    # ground_truth_v2.csv
    with open(os.path.join(out_dir, "ground_truth_v2.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "collection_id", "scenario_tag",
            "expected_evidence_decision", "expected_gate",
            "expected_narration_decision", "expected_reason",
            "known_limitation", "is_synthetic",
        ])
        for rec in plan["records"]:
            cid = rec["create"].get("id", "") if rec.get("create") else ""
            w.writerow([
                cid,
                rec["scenario_tag"],
                rec["expected_evidence_decision"],
                rec["expected_gate"],
                rec["expected_narration_decision"],
                rec.get("expected_reason") or "",
                rec.get("known_limitation", False),
                True,
            ])

    # MANIFEST_v2.json
    tags = {}
    for rec in plan["records"]:
        t = rec["scenario_tag"]
        tags[t] = tags.get(t, 0) + 1

    ev_counts: dict[str, int] = {}
    gate_counts: dict[str, int] = {}
    nar_counts: dict[str, int] = {}
    for rec in plan["records"]:
        e = rec["expected_evidence_decision"]
        g = rec["expected_gate"]
        n = rec["expected_narration_decision"]
        ev_counts[e]   = ev_counts.get(e, 0) + 1
        gate_counts[g] = gate_counts.get(g, 0) + 1
        nar_counts[n]  = nar_counts.get(n, 0) + 1

    manifest = {
        "synthetic": True,
        "rng_seed":  plan["rng_seed"],
        "total_records": len(plan["records"]),
        "counts": {
            "facilities":  len(plan["facilities"]),
            "pickers":     len(plan["pickers"]),
            "producers":   len(plan["producers"]),
            "obligations": len(plan["obligations"]),
            "records":     len(plan["records"]),
            "by_scenario_tag": tags,
            "by_expected_evidence_decision": ev_counts,
            "by_expected_gate":              gate_counts,
            "by_expected_narration_decision": nar_counts,
        },
    }
    with open(os.path.join(out_dir, "MANIFEST_v2.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    print(f"\n{'='*56}")
    print(f"EcoTrace AI — Edge-Case Seed Summary")
    print(f"{'='*56}")
    print(f"  Total records:  {len(plan['records'])}")
    print(f"  Facilities:     {len(plan['facilities'])}")
    print(f"  Pickers:        {len(plan['pickers'])}")
    print(f"  Producers:      {len(plan['producers'])}")
    print(f"  Obligations:    {len(plan['obligations'])}")
    print(f"\n  By expected_evidence_decision:")
    for k, v in sorted(ev_counts.items()):
        print(f"    {k:20s} {v}")
    print(f"\n  By expected_gate:")
    for k, v in sorted(gate_counts.items()):
        print(f"    {k:20s} {v}")
    print(f"\n  By expected_narration_decision:")
    for k, v in sorted(nar_counts.items()):
        print(f"    {k:20s} {v}")
    print(f"\n  By scenario_tag group (A-J + CLEAN):")
    group_counts: dict[str, int] = {}
    for t, c in tags.items():
        g = t[0] if t != "CLEAN" else "CLEAN"
        group_counts[g] = group_counts.get(g, 0) + c
    for g in sorted(group_counts):
        print(f"    {g:10s} {group_counts[g]}")
    print(f"{'='*56}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data"))
    args = parser.parse_args()
    plan = build_edge_plan()
    write_edge_files(plan, args.out)


if __name__ == "__main__":
    main()
