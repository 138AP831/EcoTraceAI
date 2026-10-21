"""Seed data tests: determinism, Luhn, labels, in-memory load, outcomes, integrity."""
import csv
import json
import os

from app.models import (
    BadgeReference,
    Collection,
    EvidenceAssessment,
    Facility,
    NarrationAssessment,
    ObligationRecord,
    Picker,
    Producer,
    TrustBadge,
)
from seed.generate import build_plan, write_files
from seed.load import run_load
from seed.luhn import is_valid_imei

HERE = os.path.dirname(__file__)
SEED_DATA = os.path.join(HERE, "..", "seed", "data")


# ---------------- Determinism ----------------
def test_determinism(tmp_path):
    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    write_files(build_plan(), str(d1))
    write_files(build_plan(), str(d2))
    for fname in ["plan.json", "MANIFEST.json", "ground_truth.csv"]:
        assert (d1 / fname).read_bytes() == (d2 / fname).read_bytes(), f"{fname} not deterministic"


# ---------------- Luhn ----------------
def test_luhn_imeis():
    path = os.path.join(SEED_DATA, "collections.csv")
    assert os.path.exists(path), "collections.csv missing (run seed.generate + seed.load --reset)"
    imeis = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["serial_or_imei"]:
                imeis.append(row["serial_or_imei"])
    assert len(imeis) > 0
    for imei in imeis:
        assert len(imei) == 15, imei
        assert imei.startswith("99"), imei
        assert is_valid_imei(imei), imei


# ---------------- Labels ----------------
def test_labels():
    for fname in ("facilities.csv", "producers.csv", "pickers.csv"):
        path = os.path.join(SEED_DATA, fname)
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                assert row["name"].endswith(" (synthetic)"), (fname, row["name"])
    with open(os.path.join(SEED_DATA, "facilities.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            assert row["registration_no"].startswith("SYN-"), row["registration_no"]
    with open(os.path.join(SEED_DATA, "MANIFEST.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["synthetic"] is True


# ---------------- In-memory load + comprehensive checks ----------------
def test_seed_load_comprehensive(client, session):
    plan = build_plan()
    run_load(client, plan)

    # counts
    assert session.query(Collection).count() == 120
    assert session.query(Facility).count() == 8
    assert session.query(Picker).count() == 12
    assert session.query(Producer).count() == 6
    assert session.query(ObligationRecord).count() == 14

    # outcome coverage
    evidence_decs = [e.decision for e in session.query(EvidenceAssessment).all()]
    assert "auto_verified" in evidence_decs
    assert "hitl" in evidence_decs
    # rejected-by-gate (score None, gate_failed reason)
    assert any(e.decision == "rejected" and e.score is None and "gate_failed" in e.reason
               for e in session.query(EvidenceAssessment).all())
    # rejected-by-score (score not None, rejected)
    assert any(e.decision == "rejected" and e.score is not None
               for e in session.query(EvidenceAssessment).all())
    # completion_hold
    assert session.query(Collection).filter(Collection.status == "completion_hold").count() >= 1
    # narration decisions
    nar_decs = [n.decision for n in session.query(NarrationAssessment).all()]
    assert "auto_issued" in nar_decs
    assert "hitl" in nar_decs
    assert "rejected" in nar_decs
    # badge consumed + revoked
    badge_statuses = [b.status for b in session.query(TrustBadge).all()]
    assert "consumed" in badge_statuses
    assert "revoked" in badge_statuses

    # ground truth agreement (100% across all collections incl. borderline HITL outcomes)
    mismatches = []
    for col in plan["collections"]:
        c = session.get(Collection, col["id"])
        if c.status != col["expected_final_status"]:
            mismatches.append((col["scenario"], col["id"], c.status, col["expected_final_status"]))
    assert not mismatches, f"ground truth mismatches: {mismatches[:5]}"

    # referential integrity
    for ref in session.query(BadgeReference).all():
        badge = session.get(TrustBadge, ref.badge_id)
        obl = session.get(ObligationRecord, ref.obligation_id)
        assert obl.category == badge.category, "badge ref category mismatch"
    for obl in session.query(ObligationRecord).all():
        assert obl.fulfilled_kg >= 0, "negative fulfilled_kg"

    # marketplace: default returns only unconsumed, non-revoked, all evidence >= 0.80
    r = client.get("/marketplace/badges")
    assert r.status_code == 200
    badges = r.json()
    assert len(badges) > 0
    assert all(b["status"] == "unconsumed" for b in badges)
    assert all(b["evidence_score"] >= 0.80 for b in badges)
    # exactly 2 revoked when explicitly requested
    r2 = client.get("/marketplace/badges", params={"status": "revoked"})
    assert len(r2.json()) == 2
