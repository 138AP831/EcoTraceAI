"""Replay the synthetic plan through the FastAPI app, export CSVs, print a summary.

`python -m seed.load --reset` drops+recreates the dev DB, loads everything via the
API (engine decides outcomes), exports DB tables to CSV, and prints a summary.
"""
from __future__ import annotations

import csv
import json
import os
from datetime import date, datetime

from fastapi.testclient import TestClient

import app.models  # noqa: F401  register models
from app.db import SessionLocal, drop_db, init_db
from app.main import app

HERE = os.path.dirname(__file__)
DATA_DIR = os.path.join(HERE, "data")


def run_load(client: TestClient, plan: dict):
    """POST the plan through the API in order. Returns {collection_index: badge_id}."""
    for f in plan["facilities"]:
        r = client.post("/facilities", json=f)
        assert r.status_code == 201, f"facility create failed: {r.status_code} {r.text}"
    for p in plan["pickers"]:
        r = client.post("/pickers", json=p)
        assert r.status_code == 201, f"picker create failed: {r.status_code} {r.text}"
    for p in plan["producers"]:
        r = client.post("/producers", json=p)
        assert r.status_code == 201, f"producer create failed: {r.status_code} {r.text}"
    for o in plan["obligations"]:
        r = client.post(f"/producers/{o['producer_id']}/obligations", json=o)
        assert r.status_code == 201, f"obligation create failed: {r.status_code} {r.text}"

    badge_by_index = {}
    for idx, col in enumerate(plan["collections"]):
        cid = col["id"]
        r = client.post("/collections", json=col["create"])
        assert r.status_code == 201, f"collection create failed: {r.status_code} {r.text}\n{col['create']}"
        assert r.json()["id"] == cid

        if col["evidence"]:
            client.post(f"/collections/{cid}/evidence", json=col["evidence"])
        if col["hitl_evidence"]:
            client.post(f"/collections/{cid}/hitl-approve",
                        json={"stage": "evidence", "approved": col["hitl_evidence"]["approved"]})
        if col["completion"]:
            client.post(f"/collections/{cid}/completion", json=col["completion"])
        if col["narration"]:
            r = client.post(f"/collections/{cid}/narration", json=col["narration"])
            if r.status_code == 201 and r.json().get("badge_id"):
                badge_by_index[idx] = r.json()["badge_id"]
        if col["hitl_narration"]:
            r = client.post(f"/collections/{cid}/hitl-approve",
                            json={"stage": "narration", "approved": col["hitl_narration"]["approved"]})
            if r.status_code == 200 and r.json().get("badge_id"):
                badge_by_index[idx] = r.json()["badge_id"]

    for ref in plan["badge_activity"]["references"]:
        bid = badge_by_index.get(ref["collection_index"])
        if bid:
            client.post(f"/badges/{bid}/reference",
                        json={"producer_id": ref["producer_id"], "obligation_id": ref["obligation_id"]})
    for rev in plan["badge_activity"]["revokes"]:
        bid = badge_by_index.get(rev["collection_index"])
        if bid:
            client.post(f"/badges/{bid}/revoke", json={"reason": rev["reason"]})

    return badge_by_index


def _ser(v):
    if v is None:
        return ""
    if isinstance(v, (list, dict)):
        return json.dumps(v, sort_keys=True)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


_TABLES = [
    ("facilities.csv", "facilities",
     ["id", "name", "registration_no", "authority", "state", "registration_status",
      "registration_valid_until", "geofence_lat", "geofence_lng", "geofence_radius_m",
      "authorized_categories", "daily_capacity_kg", "booked_capacity_kg", "created_at", "updated_at"]),
    ("pickers.csv", "pickers", ["id", "name", "phone", "created_at", "updated_at"]),
    ("producers.csv", "producers", ["id", "name", "state", "created_at", "updated_at"]),
    ("obligations.csv", "obligations",
     ["id", "producer_id", "category", "compliance_period", "target_kg",
      "fulfilled_kg", "created_at", "updated_at"]),
    ("collections.csv", "collections",
     ["id", "picker_id", "facility_id", "item_state", "category", "serial_or_imei",
      "declared_weight_kg", "weighbridge_weight_kg", "collection_state", "facility_state",
      "inter_state", "image_hash", "intake_at", "status", "created_at", "updated_at"]),
    ("evidence_assessments.csv", "evidence_assessments",
     ["id", "collection_id", "mode", "component_scores", "gates", "score", "decision",
      "reason", "weight_source", "created_at", "updated_at"]),
    ("completion_records.csv", "completion_records",
     ["id", "collection_id", "evidence_type", "submitted_at", "invoice_weight_kg",
      "invoice_buyer_id", "facility_revalidated", "manifest_present", "passed",
      "failure_reasons", "created_at", "updated_at"]),
    ("narration_assessments.csv", "narration_assessments",
     ["id", "collection_id", "hard_gates", "soft_scores", "score", "decision", "reason",
      "corpus_version", "sanitizer_passed", "created_at", "updated_at"]),
    ("badges.csv", "badges",
     ["id", "collection_id", "facility_id", "category", "weight_kg", "evidence_score",
      "narration_score", "status", "issued_at", "revoked_at", "revocation_reason",
      "created_at", "updated_at"]),
    ("badge_references.csv", "badge_references",
     ["id", "badge_id", "producer_id", "obligation_id", "referenced_at", "weight_kg_applied",
      "created_at", "updated_at"]),
]


def export_csvs(session, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    from app.db import engine
    from sqlalchemy import text
    for fname, table, cols in _TABLES:
        col_list = ", ".join(cols)
        rows = session.execute(text(f"SELECT {col_list} FROM {table}")).all()
        with open(os.path.join(out_dir, fname), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for row in rows:
                w.writerow([_ser(v) for v in row])


def print_summary(plan: dict, session):
    from app.models import Collection
    by_status = {}
    by_scenario = {}
    for col in plan["collections"]:
        c = session.get(Collection, col["id"])
        st = c.status
        by_status[st] = by_status.get(st, 0) + 1
        by_scenario.setdefault(col["scenario"], {})
        by_scenario[col["scenario"]][st] = by_scenario[col["scenario"]].get(st, 0) + 1

    print("=" * 56)
    print("FINAL COLLECTION STATUS COUNTS")
    print("=" * 56)
    for st in sorted(by_status):
        print(f"  {st:24s} {by_status[st]}")
    print("=" * 56)
    print("PER-SCENARIO OUTCOMES")
    print("=" * 56)
    for sc in sorted(by_scenario):
        parts = ", ".join(f"{st}={n}" for st, n in sorted(by_scenario[sc].items()))
        print(f"  {sc:24s} {parts}")


def main():
    import argparse
    from seed.generate import build_plan, write_files

    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--plan", default=os.path.join(DATA_DIR, "plan.json"))
    args = parser.parse_args()

    if args.reset:
        drop_db()
        init_db()

    if not os.path.exists(args.plan):
        plan = build_plan()
        write_files(plan, os.path.dirname(args.plan) or DATA_DIR)
    else:
        with open(args.plan, encoding="utf-8") as f:
            plan = json.load(f)

    client = TestClient(app)
    run_load(client, plan)

    session = SessionLocal()
    try:
        export_csvs(session, DATA_DIR)
        print_summary(plan, session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
