"""Deterministic synthetic scenario plan builder (stdlib only).

Builds the full plan as pure data. No DB, no FastAPI. The engine/API decide
outcomes at load time; nothing is hardcoded. Running twice (same seed) yields
byte-identical files.
"""
from __future__ import annotations

import csv
import json
import os
import random
import uuid
from datetime import datetime, timedelta

from seed.luhn import make_imei

RNG_SEED = 42
REFERENCE_NOW = datetime(2026, 10, 20, 0, 0, 0)
CORPUS_VERSION = "corpus-v1-20261020"
CATEGORIES = ["IT_telecom", "consumer_electronics", "large_appliances",
              "small_appliances", "lighting", "other"]
STATES = ["Telangana", "Karnataka", "Maharashtra", "Tamil Nadu", "Gujarat", "Delhi"]

# (name, reg_no, authority, state, status, valid_until, lat, lng, categories)
_FAC_DEFS = [
    ("Hyderabad Facility (synthetic)", "SYN-TS-0001", "TSPPCB", "Telangana", "active", "2027-03-31", 17.3850, 78.4867, ["IT_telecom", "consumer_electronics", "small_appliances"]),
    ("Bengaluru Facility (synthetic)", "SYN-KA-0002", "KSPCB", "Karnataka", "active", "2027-03-31", 12.9716, 77.5946, ["IT_telecom", "large_appliances"]),
    ("Mumbai Facility (synthetic)", "SYN-MH-0003", "MPCB", "Maharashtra", "active", "2027-03-31", 19.0760, 72.8777, ["consumer_electronics", "small_appliances", "lighting"]),
    ("Chennai Facility (synthetic)", "SYN-TN-0004", "TNPCB", "Tamil Nadu", "active", "2027-03-31", 13.0827, 80.2707, ["IT_telecom", "lighting", "other"]),
    ("Ahmedabad Facility (synthetic)", "SYN-GJ-0005", "GPCB", "Gujarat", "active", "2027-03-31", 23.0225, 72.5714, ["large_appliances", "small_appliances", "other"]),
    ("Pune Facility (synthetic)", "SYN-MH-0006", "MPCB", "Maharashtra", "active", "2026-10-30", 18.5204, 73.8567, ["IT_telecom", "consumer_electronics", "lighting"]),
    ("Expired Facility (synthetic)", "SYN-TS-0007", "TSPPCB", "Telangana", "expired", "2026-09-01", 17.3850, 78.4867, ["IT_telecom", "consumer_electronics"]),
    ("Revoked Facility (synthetic)", "SYN-KA-0008", "KSPCB", "Karnataka", "revoked", "2026-08-01", 12.9716, 77.5946, ["large_appliances", "small_appliances"]),
]

_PRODUCER_DEFS = [
    ("Producer Alpha (synthetic)", "Telangana"),
    ("Producer Beta (synthetic)", "Karnataka"),
    ("Producer Gamma (synthetic)", "Maharashtra"),
    ("Producer Delta (synthetic)", "Tamil Nadu"),
    ("Producer Epsilon (synthetic)", "Gujarat"),
    ("Producer Zeta (synthetic)", "Delhi"),
]
# category assignments per producer (cover all 6 categories, 2-3 each)
_PRODUCER_CATS = {
    0: ["IT_telecom", "consumer_electronics"],
    1: ["large_appliances", "small_appliances"],
    2: ["lighting", "other", "IT_telecom"],
    3: ["consumer_electronics", "large_appliances"],
    4: ["small_appliances", "lighting", "other"],
    5: ["IT_telecom", "other"],
}

_SCENARIOS = [
    ("clean_intact", 32),
    ("clean_dismantled", 16),
    ("borderline_evidence", 22),
    ("low_quality", 12),
    ("duplicate", 8),
    ("facility_lapsed", 5),
    ("late_completion", 6),
    ("missing_manifest", 4),
    ("invoice_mismatch", 4),
    ("numeric_mismatch", 5),
    ("narration_borderline", 6),
]


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _sig(rng, mean, sd, lo, hi):
    return round(max(lo, min(hi, rng.gauss(mean, sd))), 4)


def build_plan(rng: random.Random | None = None) -> dict:
    if rng is None:
        rng = random.Random(RNG_SEED)

    def gen_id():
        return str(uuid.UUID(int=rng.getrandbits(128), version=4))

    # ---- Facilities ----
    facilities = []
    for name, reg, auth, state, status, valid_until, lat, lng, cats in _FAC_DEFS:
        daily = rng.randint(500, 5000)
        booked = round(daily * rng.uniform(0.10, 0.80))
        radius = rng.randint(150, 400)
        facilities.append({
            "id": gen_id(), "name": name, "registration_no": reg, "authority": auth,
            "state": state, "registration_status": status,
            "registration_valid_until": valid_until,
            "geofence_lat": lat, "geofence_lng": lng, "geofence_radius_m": radius,
            "authorized_categories": cats, "daily_capacity_kg": daily,
            "booked_capacity_kg": booked,
        })
    active_fac_ids = [f["id"] for f in facilities if f["registration_status"] == "active"]
    lapsed_fac_ids = [f["id"] for f in facilities if f["registration_status"] in ("expired", "revoked")]
    fac_by_id = {f["id"]: f for f in facilities}

    # ---- Pickers ----
    pickers = []
    used_phones = set()
    for i in range(12):
        phone = "90000" + ("%05d" % rng.randint(0, 99999))
        while phone in used_phones:
            phone = "90000" + ("%05d" % rng.randint(0, 99999))
        used_phones.add(phone)
        pickers.append({"id": gen_id(), "name": f"Picker {i + 1:02d} (synthetic)", "phone": phone})

    # ---- Producers + obligations ----
    producers = [{"id": gen_id(), "name": name, "state": state} for name, state in _PRODUCER_DEFS]
    obligations = []
    obligations_by_category = {c: [] for c in CATEGORIES}
    for pi, cat_list in _PRODUCER_CATS.items():
        for cat in cat_list:
            oid = gen_id()
            obligations.append({
                "id": oid, "producer_id": producers[pi]["id"], "category": cat,
                "compliance_period": "FY2026-27", "target_kg": rng.randint(1000, 20000),
                "fulfilled_kg": 0,
            })
            obligations_by_category[cat].append((oid, producers[pi]["id"]))

    # ---- Collections ----
    collections = []
    clean_intact_indices = []
    borderline_approved_indices = []
    narration_borderline_approved_indices = []

    fac_counter = {"i": 0}
    picker_counter = {"i": 0}
    used_hashes = set()

    def new_hash():
        h = "%016x" % rng.getrandbits(64)
        while h in used_hashes:
            h = "%016x" % rng.getrandbits(64)
        used_hashes.add(h)
        return h

    def pick_active_fac():
        fid = active_fac_ids[fac_counter["i"] % len(active_fac_ids)]
        fac_counter["i"] += 1
        return fid

    def pick_picker():
        pid = pickers[picker_counter["i"] % len(pickers)]["id"]
        picker_counter["i"] += 1
        return pid

    base = datetime(2026, 4, 1)
    span = (datetime(2026, 10, 15) - base).total_seconds()

    def intake_at():
        t = base + timedelta(seconds=rng.uniform(0, span))
        return t.replace(microsecond=0)

    def choose_state(fac_state, force_inter=False):
        if force_inter or rng.random() < 0.25:
            others = [s for s in STATES if s != fac_state]
            return rng.choice(others)
        return fac_state

    def make_create(fid, item_state, category, collection_state, declared, wb_kg, serial, image_hash, t_in):
        return {
            "id": gen_id(), "picker_id": pick_picker(), "facility_id": fid,
            "item_state": item_state, "category": category, "serial_or_imei": serial,
            "declared_weight_kg": declared, "weighbridge_weight_kg": wb_kg,
            "collection_state": collection_state, "image_hash": image_hash,
            "intake_at": _iso(t_in),
        }

    def build_ev(item_state, mean, sd, lo, hi, fac_active, dup, wb_present):
        body = {"duplicate_detected": dup, "facility_registration_active": fac_active}

        def s():
            return _sig(rng, mean, sd, lo, hi)

        if item_state == "intact":
            body["device_serial_confidence"] = s()
            body["serial_uniqueness"] = s()
        else:
            body["component_classification_confidence"] = s()
            body["material_composition_plausibility"] = s()
        body["facility_registration_validity"] = s()
        body["gps_validity"] = s()
        body["image_quality"] = s()
        body["declared_weight_consistency"] = s()
        if wb_present:
            body["weighbridge_weight_consistency"] = s()
        return body

    def clean_completion(et, t_in, wb_kg):
        sub = (t_in + timedelta(hours=round(rng.uniform(2, 60), 2))).replace(microsecond=0)
        body = {"submitted_at": _iso(sub), "evidence_type": et,
                "facility_registration_active_now": True, "manifest_present": True}
        if et in ("sales_invoice", "both"):
            body["invoice_weight_kg"] = round(wb_kg * rng.uniform(0.97, 1.03), 2)
            body["invoice_buyer_id"] = "BUYER-%04d" % rng.randint(0, 9999)
        return body

    def narration_high():
        def s():
            return _sig(rng, 0.93, 0.04, 0.88, 1.0)
        return {"sanitizer_passed": True, "numeric_verification_passed": True,
                "uniqueness_check_passed": True, "corpus_version": CORPUS_VERSION,
                "regulatory_grounding": s(), "cross_document_consistency": s(),
                "chronological_consistency": s(), "no_gaming_flags": s()}

    def narration_borderline():
        def s():
            return _sig(rng, 0.72, 0.05, 0.62, 0.82)
        return {"sanitizer_passed": True, "numeric_verification_passed": True,
                "uniqueness_check_passed": True, "corpus_version": CORPUS_VERSION,
                "regulatory_grounding": s(), "cross_document_consistency": s(),
                "chronological_consistency": s(), "no_gaming_flags": s()}

    def add(scenario, expected, create, evidence, hitl_ev, completion, narration, hitl_nar):
        idx = len(collections)
        collections.append({
            "id": create["id"], "scenario": scenario, "expected_final_status": expected,
            "create": create, "evidence": evidence, "hitl_evidence": hitl_ev,
            "completion": completion, "narration": narration, "hitl_narration": hitl_nar,
        })
        return idx

    def gen_common(scenario_for_fac, force_inter=False, fac_id=None):
        """Pick facility/picker/category/state/weight/serial/hash/intake for a collection."""
        if fac_id is None:
            fac_id = pick_active_fac()
        fac = fac_by_id[fac_id]
        item_state = "intact" if rng.random() < 0.7 else "dismantled"
        if scenario_for_fac == "clean_intact":
            item_state = "intact"
        elif scenario_for_fac == "clean_dismantled":
            item_state = "dismantled"
        category = rng.choice(fac["authorized_categories"])
        cstate = choose_state(fac["state"], force_inter=force_inter)
        declared = round(2 + (60 - 2) * (rng.random() ** 2), 2)
        return fac_id, item_state, category, cstate, declared

    # ---- clean_intact ----
    for _ in range(32):
        fid, item_state, category, cstate, declared = gen_common("clean_intact")
        t_in = intake_at()
        et = rng.choices(["destruction_media", "sales_invoice", "both"], weights=[50, 25, 25], k=1)[0]
        wb_present = (et in ("sales_invoice", "both")) or (rng.random() < 0.7)
        wb_kg = round(declared * rng.uniform(0.95, 1.05), 2) if wb_present else None
        serial = make_imei(rng)
        h = new_hash()
        create = make_create(fid, item_state, category, cstate, declared, wb_kg, serial, h, t_in)
        ev = build_ev(item_state, 0.92, 0.04, 0.85, 1.0, True, False, wb_present)
        comp = clean_completion(et, t_in, wb_kg)
        nar = narration_high()
        idx = add("clean_intact", "badge_issued", create, ev, None, comp, nar, None)
        clean_intact_indices.append(idx)

    # ---- clean_dismantled ----
    for _ in range(16):
        fid, item_state, category, cstate, declared = gen_common("clean_dismantled")
        t_in = intake_at()
        et = rng.choices(["destruction_media", "sales_invoice", "both"], weights=[50, 25, 25], k=1)[0]
        wb_present = (et in ("sales_invoice", "both")) or (rng.random() < 0.7)
        wb_kg = round(declared * rng.uniform(0.95, 1.05), 2) if wb_present else None
        serial = None
        h = new_hash()
        create = make_create(fid, item_state, category, cstate, declared, wb_kg, serial, h, t_in)
        ev = build_ev(item_state, 0.92, 0.04, 0.85, 1.0, True, False, wb_present)
        comp = clean_completion(et, t_in, wb_kg)
        nar = narration_high()
        add("clean_dismantled", "badge_issued", create, ev, None, comp, nar, None)

    # ---- borderline_evidence ----
    for i in range(22):
        fid, item_state, category, cstate, declared = gen_common("borderline_evidence")
        t_in = intake_at()
        wb_present = rng.random() < 0.7
        wb_kg = round(declared * rng.uniform(0.95, 1.05), 2) if wb_present else None
        serial = make_imei(rng) if item_state == "intact" else None
        h = new_hash()
        create = make_create(fid, item_state, category, cstate, declared, wb_kg, serial, h, t_in)
        ev = build_ev(item_state, 0.68, 0.08, 0.60, 0.78, True, False, wb_present)
        approved = i < 11
        if approved:
            et = rng.choices(["destruction_media", "sales_invoice", "both"], weights=[50, 25, 25], k=1)[0]
            # ensure weighbridge present for invoice evidence types
            if et in ("sales_invoice", "both") and wb_kg is None:
                wb_kg = round(declared * rng.uniform(0.95, 1.05), 2)
                create["weighbridge_weight_kg"] = wb_kg
                ev["weighbridge_weight_consistency"] = _sig(rng, 0.68, 0.08, 0.60, 0.78)
            comp = clean_completion(et, t_in, wb_kg)
            nar = narration_high()
            idx = add("borderline_evidence", "badge_issued", create, ev, {"approved": True}, comp, nar, None)
            borderline_approved_indices.append(idx)
        else:
            add("borderline_evidence", "evidence_rejected", create, ev, {"approved": False}, None, None, None)

    # ---- low_quality ----
    for _ in range(12):
        fid, item_state, category, cstate, declared = gen_common("low_quality")
        t_in = intake_at()
        wb_present = rng.random() < 0.7
        wb_kg = round(declared * rng.uniform(0.95, 1.05), 2) if wb_present else None
        serial = make_imei(rng) if item_state == "intact" else None
        h = new_hash()
        create = make_create(fid, item_state, category, cstate, declared, wb_kg, serial, h, t_in)
        ev = build_ev(item_state, 0.35, 0.10, 0.0, 0.50, True, False, wb_present)
        add("low_quality", "evidence_rejected", create, ev, None, None, None, None)

    # ---- duplicate ---- (copy image_hash from an earlier clean_intact at same facility)
    for j in range(8):
        src = collections[clean_intact_indices[j]]
        fid = src["create"]["facility_id"]
        fac = fac_by_id[fid]
        item_state = "intact" if rng.random() < 0.7 else "dismantled"
        category = rng.choice(fac["authorized_categories"])
        cstate = choose_state(fac["state"])
        declared = round(2 + (60 - 2) * (rng.random() ** 2), 2)
        t_in = intake_at()
        wb_present = rng.random() < 0.7
        wb_kg = round(declared * rng.uniform(0.95, 1.05), 2) if wb_present else None
        serial = make_imei(rng) if item_state == "intact" else None
        h = src["create"]["image_hash"]  # duplicate hash
        create = make_create(fid, item_state, category, cstate, declared, wb_kg, serial, h, t_in)
        ev = build_ev(item_state, 0.92, 0.04, 0.85, 1.0, True, True, wb_present)
        add("duplicate", "evidence_rejected", create, ev, None, None, None, None)

    # ---- facility_lapsed ----
    for i in range(5):
        fid = lapsed_fac_ids[i % len(lapsed_fac_ids)]
        fac = fac_by_id[fid]
        item_state = "intact" if rng.random() < 0.7 else "dismantled"
        category = rng.choice(fac["authorized_categories"])
        cstate = choose_state(fac["state"])
        declared = round(2 + (60 - 2) * (rng.random() ** 2), 2)
        t_in = intake_at()
        wb_present = rng.random() < 0.7
        wb_kg = round(declared * rng.uniform(0.95, 1.05), 2) if wb_present else None
        serial = make_imei(rng) if item_state == "intact" else None
        h = new_hash()
        create = make_create(fid, item_state, category, cstate, declared, wb_kg, serial, h, t_in)
        ev = build_ev(item_state, 0.92, 0.04, 0.85, 1.0, False, False, wb_present)
        add("facility_lapsed", "evidence_rejected", create, ev, None, None, None, None)

    # ---- late_completion ----
    for _ in range(6):
        fid, item_state, category, cstate, declared = gen_common("late_completion")
        t_in = intake_at()
        wb_present = rng.random() < 0.7
        wb_kg = round(declared * rng.uniform(0.95, 1.05), 2) if wb_present else None
        serial = make_imei(rng) if item_state == "intact" else None
        h = new_hash()
        create = make_create(fid, item_state, category, cstate, declared, wb_kg, serial, h, t_in)
        ev = build_ev(item_state, 0.92, 0.04, 0.85, 1.0, True, False, wb_present)
        sub = (t_in + timedelta(hours=round(rng.uniform(80, 120), 2))).replace(microsecond=0)
        comp = {"submitted_at": _iso(sub), "evidence_type": "destruction_media",
                "facility_registration_active_now": True, "manifest_present": True}
        add("late_completion", "completion_hold", create, ev, None, comp, None, None)

    # ---- missing_manifest ----
    for _ in range(4):
        fid, item_state, category, cstate, declared = gen_common("missing_manifest", force_inter=True)
        t_in = intake_at()
        wb_present = rng.random() < 0.7
        wb_kg = round(declared * rng.uniform(0.95, 1.05), 2) if wb_present else None
        serial = make_imei(rng) if item_state == "intact" else None
        h = new_hash()
        create = make_create(fid, item_state, category, cstate, declared, wb_kg, serial, h, t_in)
        ev = build_ev(item_state, 0.92, 0.04, 0.85, 1.0, True, False, wb_present)
        sub = (t_in + timedelta(hours=round(rng.uniform(2, 60), 2))).replace(microsecond=0)
        comp = {"submitted_at": _iso(sub), "evidence_type": "destruction_media",
                "facility_registration_active_now": True, "manifest_present": False}
        add("missing_manifest", "completion_hold", create, ev, None, comp, None, None)

    # ---- invoice_mismatch ----
    for _ in range(4):
        fid, item_state, category, cstate, declared = gen_common("invoice_mismatch")
        t_in = intake_at()
        wb_kg = round(declared * rng.uniform(0.95, 1.05), 2)  # always present (invoice used)
        serial = make_imei(rng) if item_state == "intact" else None
        h = new_hash()
        create = make_create(fid, item_state, category, cstate, declared, wb_kg, serial, h, t_in)
        ev = build_ev(item_state, 0.92, 0.04, 0.85, 1.0, True, False, True)
        sub = (t_in + timedelta(hours=round(rng.uniform(2, 60), 2))).replace(microsecond=0)
        off = rng.uniform(0.08, 0.15)
        inv = round(wb_kg * (1 + off), 2)
        comp = {"submitted_at": _iso(sub), "evidence_type": "sales_invoice",
                "facility_registration_active_now": True, "manifest_present": True,
                "invoice_weight_kg": inv, "invoice_buyer_id": "BUYER-%04d" % rng.randint(0, 9999)}
        add("invoice_mismatch", "completion_hold", create, ev, None, comp, None, None)

    # ---- numeric_mismatch ----
    for _ in range(5):
        fid, item_state, category, cstate, declared = gen_common("numeric_mismatch")
        t_in = intake_at()
        et = rng.choices(["destruction_media", "sales_invoice", "both"], weights=[50, 25, 25], k=1)[0]
        wb_present = (et in ("sales_invoice", "both")) or (rng.random() < 0.7)
        wb_kg = round(declared * rng.uniform(0.95, 1.05), 2) if wb_present else None
        serial = make_imei(rng) if item_state == "intact" else None
        h = new_hash()
        create = make_create(fid, item_state, category, cstate, declared, wb_kg, serial, h, t_in)
        ev = build_ev(item_state, 0.92, 0.04, 0.85, 1.0, True, False, wb_present)
        comp = clean_completion(et, t_in, wb_kg)
        nar = narration_high()
        nar["numeric_verification_passed"] = False
        add("numeric_mismatch", "narration_rejected", create, ev, None, comp, nar, None)

    # ---- narration_borderline ----
    for i in range(6):
        fid, item_state, category, cstate, declared = gen_common("narration_borderline")
        t_in = intake_at()
        et = rng.choices(["destruction_media", "sales_invoice", "both"], weights=[50, 25, 25], k=1)[0]
        wb_present = (et in ("sales_invoice", "both")) or (rng.random() < 0.7)
        wb_kg = round(declared * rng.uniform(0.95, 1.05), 2) if wb_present else None
        serial = make_imei(rng) if item_state == "intact" else None
        h = new_hash()
        create = make_create(fid, item_state, category, cstate, declared, wb_kg, serial, h, t_in)
        ev = build_ev(item_state, 0.92, 0.04, 0.85, 1.0, True, False, wb_present)
        comp = clean_completion(et, t_in, wb_kg)
        nar = narration_borderline()
        approved = i < 3
        idx = add("narration_borderline",
                  "badge_issued" if approved else "narration_rejected",
                  create, ev, None, comp, nar, {"approved": approved})
        if approved:
            narration_borderline_approved_indices.append(idx)

    # ---- Badge activity ----
    references = []
    # reference all borderline-approved (consume low-evidence badges) + 9 clean_intact
    ref_targets = borderline_approved_indices + clean_intact_indices[:9]
    for idx in ref_targets:
        col_cat = collections[idx]["create"]["category"]
        obl_id, prod_id = obligations_by_category[col_cat][0]
        references.append({"collection_index": idx, "producer_id": prod_id, "obligation_id": obl_id})

    revokes = []
    # one consumed (first referenced = borderline-approved) and one unconsumed clean_intact
    revokes.append({"collection_index": borderline_approved_indices[0], "reason": "audit_reopen_consumed"})
    revokes.append({"collection_index": clean_intact_indices[9], "reason": "compliance_audit_unconsumed"})

    plan = {
        "reference_now": _iso(REFERENCE_NOW),
        "rng_seed": RNG_SEED,
        "facilities": facilities,
        "pickers": pickers,
        "producers": producers,
        "obligations": obligations,
        "collections": collections,
        "badge_activity": {"references": references, "revokes": revokes},
    }
    return plan


def write_files(plan: dict, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, sort_keys=True)
    # MANIFEST.json
    scenario_counts = {}
    for c in plan["collections"]:
        scenario_counts[c["scenario"]] = scenario_counts.get(c["scenario"], 0) + 1
    manifest = {
        "synthetic": True,
        "rng_seed": plan["rng_seed"],
        "counts": {
            "facilities": len(plan["facilities"]),
            "pickers": len(plan["pickers"]),
            "producers": len(plan["producers"]),
            "obligations": len(plan["obligations"]),
            "collections": len(plan["collections"]),
            "scenarios": scenario_counts,
        },
    }
    with open(os.path.join(out_dir, "MANIFEST.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    # ground_truth.csv (from plan only)
    with open(os.path.join(out_dir, "ground_truth.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["collection_id", "scenario", "expected_final_status"])
        for c in plan["collections"]:
            w.writerow([c["id"], c["scenario"], c["expected_final_status"]])


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data"))
    args = parser.parse_args()
    plan = build_plan()
    write_files(plan, args.out)
    print(f"Wrote plan.json, MANIFEST.json, ground_truth.csv to {args.out}")
    print(f"  facilities={len(plan['facilities'])} pickers={len(plan['pickers'])} "
          f"producers={len(plan['producers'])} obligations={len(plan['obligations'])} "
          f"collections={len(plan['collections'])}")


if __name__ == "__main__":
    main()
