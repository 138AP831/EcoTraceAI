"""API flow tests via TestClient against fresh in-memory SQLite."""
from datetime import datetime, timedelta

from app.models import ObligationRecord, TrustBadge


def _make_facility(client, state="Telangana", categories=None):
    if categories is None:
        categories = ["IT_telecom", "consumer_electronics"]
    r = client.post("/facilities", json={
        "name": "Acme Recycling (synthetic)",
        "registration_no": "SYN-TS-0001",
        "authority": "CPCB",
        "state": state,
        "registration_status": "active",
        "registration_valid_until": "2027-03-31",
        "geofence_lat": 17.385,
        "geofence_lng": 78.4867,
        "geofence_radius_m": 300.0,
        "authorized_categories": categories,
        "daily_capacity_kg": 2000.0,
        "booked_capacity_kg": 500.0,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _make_picker(client, phone="9000011111"):
    r = client.post("/pickers", json={"name": "Ravi (synthetic)", "phone": phone})
    assert r.status_code == 201, r.text
    return r.json()


def _make_producer(client, state="Telangana"):
    r = client.post("/producers", json={"name": "Producer One (synthetic)", "state": state})
    assert r.status_code == 201, r.text
    return r.json()


def _make_obligation(client, producer_id, category="IT_telecom", target=100.0, period="FY2026-27"):
    r = client.post(f"/producers/{producer_id}/obligations", json={
        "category": category, "compliance_period": period, "target_kg": target,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _make_collection(client, picker_id, facility_id, category="IT_telecom",
                     declared=12.0, weighbridge=12.0, state="Telangana",
                     item_state="intact", intake_at="2026-06-01T10:00:00",
                     image_hash="abcdef0123456789", serial="99000000000001"):
    body = {
        "picker_id": picker_id,
        "facility_id": facility_id,
        "item_state": item_state,
        "category": category,
        "serial_or_imei": serial if item_state == "intact" else None,
        "declared_weight_kg": declared,
        "weighbridge_weight_kg": weighbridge,
        "collection_state": state,
        "image_hash": image_hash,
        "intake_at": intake_at,
    }
    r = client.post("/collections", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _evidence_body(**over):
    body = dict(
        duplicate_detected=False,
        facility_registration_active=True,
        device_serial_confidence=0.95,
        serial_uniqueness=1.0,
        facility_registration_validity=1.0,
        gps_validity=0.95,
        image_quality=0.90,
        weighbridge_weight_consistency=0.95,
    )
    body.update(over)
    return body


def _completion_body(**over):
    body = dict(
        submitted_at="2026-06-01T20:00:00",
        evidence_type="destruction_media",
        facility_registration_active_now=True,
        manifest_present=True,
    )
    body.update(over)
    return body


def _narration_body(**over):
    body = dict(
        sanitizer_passed=True,
        numeric_verification_passed=True,
        uniqueness_check_passed=True,
        regulatory_grounding=0.95,
        cross_document_consistency=0.95,
        chronological_consistency=0.95,
        no_gaming_flags=0.95,
        corpus_version="corpus-v1",
    )
    body.update(over)
    return body


# ----------------------------------------------------------------------
# Happy path
# ----------------------------------------------------------------------
def test_full_happy_path(client, session):
    fac = _make_facility(client)
    picker = _make_picker(client)
    producer = _make_producer(client)
    obl = _make_obligation(client, producer["id"], category="IT_telecom", target=100.0)

    col = _make_collection(client, picker["id"], fac["id"], category="IT_telecom",
                            declared=12.0, weighbridge=12.0, state="Telangana")

    # evidence -> auto_verified
    r = client.post(f"/collections/{col['id']}/evidence", json=_evidence_body())
    assert r.status_code == 201, r.text
    assert r.json()["decision"] == "auto_verified"

    # completion -> passed
    r = client.post(f"/collections/{col['id']}/completion", json=_completion_body())
    assert r.status_code == 201, r.text
    assert r.json()["passed"] is True

    # narration -> auto_issued -> badge created
    r = client.post(f"/collections/{col['id']}/narration", json=_narration_body())
    assert r.status_code == 201, r.text
    assert r.json()["decision"] == "auto_issued"
    badge_id = r.json()["badge_id"]
    assert badge_id

    # badge in marketplace
    r = client.get("/marketplace/badges", params={"category": "IT_telecom"})
    assert r.status_code == 200
    ids = [b["id"] for b in r.json()]
    assert badge_id in ids

    # reference -> fulfilled_kg == 12
    r = client.post(f"/badges/{badge_id}/reference", json={
        "producer_id": producer["id"], "obligation_id": obl["id"],
    })
    assert r.status_code == 201, r.text
    assert r.json()["obligation_fulfilled_kg"] == 12.0
    assert session.get(ObligationRecord, obl["id"]).fulfilled_kg == 12.0

    # second reference -> 409
    r = client.post(f"/badges/{badge_id}/reference", json={
        "producer_id": producer["id"], "obligation_id": obl["id"],
    })
    assert r.status_code == 409

    # revoke (consumed) -> fulfilled_kg == 0, grace_until returned
    r = client.post(f"/badges/{badge_id}/revoke", json={"reason": "fraud_detected"})
    assert r.status_code == 200, r.text
    assert r.json()["new_status"] == "revoked"
    assert r.json()["grace_until"] is not None
    assert session.get(ObligationRecord, obl["id"]).fulfilled_kg == 0.0

    # badge absent from default marketplace
    r = client.get("/marketplace/badges")
    ids = [b["id"] for b in r.json()]
    assert badge_id not in ids
    # but present when status=revoked explicitly
    r = client.get("/marketplace/badges", params={"status": "revoked"})
    assert badge_id in [b["id"] for b in r.json()]


# ----------------------------------------------------------------------
# State machine enforcement
# ----------------------------------------------------------------------
def test_evidence_twice_409(client):
    fac = _make_facility(client)
    picker = _make_picker(client)
    col = _make_collection(client, picker["id"], fac["id"])
    r = client.post(f"/collections/{col['id']}/evidence", json=_evidence_body())
    assert r.status_code == 201
    r = client.post(f"/collections/{col['id']}/evidence", json=_evidence_body())
    assert r.status_code == 409


def test_narration_before_completion_409(client):
    fac = _make_facility(client)
    picker = _make_picker(client)
    col = _make_collection(client, picker["id"], fac["id"])
    client.post(f"/collections/{col['id']}/evidence", json=_evidence_body())
    r = client.post(f"/collections/{col['id']}/narration", json=_narration_body())
    assert r.status_code == 409


def test_completion_failure_hold_then_resubmit(client):
    fac = _make_facility(client)
    picker = _make_picker(client)
    col = _make_collection(client, picker["id"], fac["id"],
                           intake_at="2026-06-01T10:00:00")
    client.post(f"/collections/{col['id']}/evidence", json=_evidence_body())
    # late completion -> hold
    late = (datetime(2026, 6, 1, 10, 0, 0) + timedelta(hours=100)).isoformat()
    r = client.post(f"/collections/{col['id']}/completion", json=_completion_body(submitted_at=late))
    assert r.status_code == 201
    assert r.json()["passed"] is False
    assert r.json()["collection_status"] == "completion_hold"
    # narration refused from hold
    r = client.post(f"/collections/{col['id']}/narration", json=_narration_body())
    assert r.status_code == 409
    # resubmit valid completion from hold -> passed
    r = client.post(f"/collections/{col['id']}/completion", json=_completion_body(
        submitted_at="2026-06-01T20:00:00"))
    assert r.status_code == 201
    assert r.json()["passed"] is True
    assert r.json()["collection_status"] == "completion_passed"


def test_evidence_hitl_approve_true(client):
    fac = _make_facility(client)
    picker = _make_picker(client)
    col = _make_collection(client, picker["id"], fac["id"])
    # borderline signals -> hitl
    r = client.post(f"/collections/{col['id']}/evidence", json=_evidence_body(
        device_serial_confidence=0.68, serial_uniqueness=0.68,
        facility_registration_validity=0.68, gps_validity=0.68,
        image_quality=0.68, weighbridge_weight_consistency=0.68))
    assert r.status_code == 201
    assert r.json()["decision"] == "hitl"
    r = client.post(f"/collections/{col['id']}/hitl-approve",
                    json={"stage": "evidence", "approved": True})
    assert r.status_code == 200
    assert r.json()["new_status"] == "evidence_verified"


def test_evidence_hitl_approve_false(client):
    fac = _make_facility(client)
    picker = _make_picker(client)
    col = _make_collection(client, picker["id"], fac["id"])
    client.post(f"/collections/{col['id']}/evidence", json=_evidence_body(
        device_serial_confidence=0.68, serial_uniqueness=0.68,
        facility_registration_validity=0.68, gps_validity=0.68,
        image_quality=0.68, weighbridge_weight_consistency=0.68))
    r = client.post(f"/collections/{col['id']}/hitl-approve",
                    json={"stage": "evidence", "approved": False})
    assert r.status_code == 200
    assert r.json()["new_status"] == "evidence_rejected"


def test_narration_hitl_approve_true_issues_badge(client):
    fac = _make_facility(client)
    picker = _make_picker(client)
    producer = _make_producer(client)
    obl = _make_obligation(client, producer["id"], category="IT_telecom")
    col = _make_collection(client, picker["id"], fac["id"])
    client.post(f"/collections/{col['id']}/evidence", json=_evidence_body())
    client.post(f"/collections/{col['id']}/completion", json=_completion_body())
    # narration hitl
    r = client.post(f"/collections/{col['id']}/narration", json=_narration_body(
        regulatory_grounding=0.72, cross_document_consistency=0.72,
        chronological_consistency=0.72, no_gaming_flags=0.72))
    assert r.json()["decision"] == "hitl"
    r = client.post(f"/collections/{col['id']}/hitl-approve",
                    json={"stage": "narration", "approved": True})
    assert r.status_code == 200
    assert r.json()["new_status"] == "badge_issued"
    badge_id = r.json()["badge_id"]
    # badge exists in marketplace
    r = client.get("/marketplace/badges", params={"category": "IT_telecom"})
    assert badge_id in [b["id"] for b in r.json()]


def test_reference_different_category_409(client):
    fac = _make_facility(client, categories=["IT_telecom", "consumer_electronics"])
    picker = _make_picker(client)
    producer = _make_producer(client)
    # obligation of a different category than the badge (IT_telecom)
    obl = _make_obligation(client, producer["id"], category="consumer_electronics")
    col = _make_collection(client, picker["id"], fac["id"], category="IT_telecom")
    client.post(f"/collections/{col['id']}/evidence", json=_evidence_body())
    client.post(f"/collections/{col['id']}/completion", json=_completion_body())
    badge_id = client.post(f"/collections/{col['id']}/narration", json=_narration_body()).json()["badge_id"]
    r = client.post(f"/badges/{badge_id}/reference", json={
        "producer_id": producer["id"], "obligation_id": obl["id"],
    })
    assert r.status_code == 409
    assert "category_mismatch" in r.json()["detail"]


def test_reference_obligation_not_belonging_to_producer_422(client):
    fac = _make_facility(client)
    picker = _make_picker(client)
    p1 = _make_producer(client, state="Karnataka")
    p2 = _make_producer(client, state="Tamil Nadu")
    obl = _make_obligation(client, p1["id"], category="IT_telecom")
    col = _make_collection(client, picker["id"], fac["id"], category="IT_telecom")
    client.post(f"/collections/{col['id']}/evidence", json=_evidence_body())
    client.post(f"/collections/{col['id']}/completion", json=_completion_body())
    badge_id = client.post(f"/collections/{col['id']}/narration", json=_narration_body()).json()["badge_id"]
    # reference against p2 but obligation belongs to p1
    r = client.post(f"/badges/{badge_id}/reference", json={
        "producer_id": p2["id"], "obligation_id": obl["id"],
    })
    assert r.status_code == 422


# ----------------------------------------------------------------------
# Marketplace filters
# ----------------------------------------------------------------------
def test_marketplace_filters(client):
    fac = _make_facility(client, categories=["IT_telecom", "lighting"])
    picker = _make_picker(client)
    col_it = _make_collection(client, picker["id"], fac["id"], category="IT_telecom",
                              image_hash="it000000000001", serial="99000000000001")
    col_light = _make_collection(client, picker["id"], fac["id"], category="lighting",
                                 image_hash="lt000000000002", serial="99000000000002")
    for col in (col_it, col_light):
        client.post(f"/collections/{col['id']}/evidence", json=_evidence_body())
        client.post(f"/collections/{col['id']}/completion", json=_completion_body())
        client.post(f"/collections/{col['id']}/narration", json=_narration_body())

    # category filter actually filters
    r = client.get("/marketplace/badges", params={"category": "lighting"})
    cats = {b["category"] for b in r.json()}
    assert cats == {"lighting"}

    # min_evidence_score filter actually filters (all ours are ~0.95 -> >= 0.97 yields none)
    r = client.get("/marketplace/badges", params={"min_evidence_score": 0.97})
    assert r.json() == []
    # but >= 0.90 returns both
    r = client.get("/marketplace/badges", params={"min_evidence_score": 0.90})
    assert len(r.json()) == 2
