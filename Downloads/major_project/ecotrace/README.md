# EcoTrace AI — backend core (STEP 1 OF N, COMPLETE)

EcoTrace AI verifies e-waste (electronic waste only, not plastic) collection and
recycling events for India's EPR compliance. It issues a **Trust Badge** — a technical
verification attestation, **NOT** a legal EPR certificate. The word "certificate" must
never appear in code, API fields, comments, or docs.

Two independent scores that must **never** be blended into one number:
1. **Evidence Trust Score** — physical-event verification (non-GenAI).
2. **Narration Confidence** — checks a generated narrative against verified evidence.

> This README doubles as the continuation prompt for the remaining pending work (below).

## What is built and verified (Step 1)

Full pytest suite passes (58 tests). Implemented:
- `app/config.py` — all weights/thresholds/windows as the ONLY literals + sum-to-1.0 assertions.
- `app/db.py`, `app/models.py` — SQLAlchemy 2.0 typed declarative models, naive UTC, Postgres-compatible.
- `app/engine/` — pure functions: `evidence.py`, `completion.py`, `narration.py`, `badge_state.py`.
  No sqlalchemy/fastapi/app.models imports; weights come from config only (no literals in engine).
- `app/schemas.py`, `app/routers/` (facilities, producers, collections+pickers, badges, marketplace),
  `app/main.py`, `app/services.py` — FastAPI REST API enforcing the collection state machine (409 on
  illegal transitions). Codes: 201 create, 404 missing, 409 state/lock, 422 validation.
- `tests/` — `test_evidence`, `test_completion`, `test_narration`, `test_badge_state`,
  `test_api_flow`, `test_seed` (in-memory SQLite, StaticPool, fresh DB per test).
- `seed/` — deterministic synthetic dataset (stdlib only): `luhn.py`, `generate.py`, `load.py`,
  and committed outputs in `seed/data/` (plan.json, MANIFEST.json, ground_truth.csv + 10 DB CSVs).

Collection state machine (enforced in routers):
```
submitted --evidence--> evidence_verified | evidence_hitl | evidence_rejected
evidence_hitl --hitl-approve(evidence)--> evidence_verified | evidence_rejected
evidence_verified | completion_hold --completion--> completion_passed | completion_hold
completion_passed --narration--> badge_issued | narration_hitl | narration_rejected
narration_hitl --hitl-approve(narration)--> badge_issued | narration_rejected
```
Badge lifecycle: unconsumed -> (reference) consumed -> (revoke) revoked; revoke of a consumed
badge reopens its obligation with a 30-day grace window.

## Quick start (run everything from the `ecotrace/` directory)

### 1. Install dependencies
```
python -m pip install -r requirements.txt
```

### 2. Run the full test suite
```
python -m pytest -q
```
Expected output:
```
.......................................................................
.................................................................        [100%]
============================== warnings summary ===============================
tests/test_edge_cases.py::TestSeedIntegrity::test_engine_vs_labels_collect_mismatches
  UserWarning: 9 seed mismatches written to SEED_MISMATCHES.md
137 passed, 1 warning in ~16s
```
The 9 seed mismatches are all documented missing features — not logic errors.
To run only the edge-case tests:
```
python -m pytest tests/test_edge_cases.py -q
```

### 3. Load the original seed (120 collections, 11 scenarios)
```
python -m seed.generate
python -m seed.load --reset
```
Expected output:
```
========================================================
FINAL COLLECTION STATUS COUNTS
========================================================
  badge_issued             62
  completion_hold          14
  evidence_rejected        36
  narration_rejected        8
========================================================
PER-SCENARIO OUTCOMES
  borderline_evidence      badge_issued=11, evidence_rejected=11
  clean_dismantled         badge_issued=16
  clean_intact             badge_issued=32
  duplicate                evidence_rejected=8
  facility_lapsed          evidence_rejected=5
  invoice_mismatch         completion_hold=4
  late_completion          completion_hold=6
  low_quality              evidence_rejected=12
  missing_manifest         completion_hold=4
  narration_borderline     badge_issued=3, narration_rejected=3
  numeric_mismatch         narration_rejected=5
```
Output files written to `seed/data/`:
- `plan.json`, `MANIFEST.json`, `ground_truth.csv`
- One CSV per DB table (facilities, collections, badges, etc.)

### 4. Load the edge-case seed (~205 records, scenarios A–J)
```
python -m seed.load --reset --edge
```
Expected output:
```
========================================================
EcoTrace AI — Edge-Case Seed Summary
========================================================
  Total records:  205
  Facilities:     6
  Pickers:        5
  Producers:      3
  Obligations:    4

  By expected_evidence_decision:
    NOT_APPLICABLE       ...
    REJECTED             ...
    REVIEW               ...
    VERIFIED             ...

  By expected_gate:
    HOLD                 ...
    NOT_APPLICABLE       ...
    PASS                 ...

  By scenario_tag group (A-J + CLEAN):
    A          11
    B          12
    C          14
    D           8
    E          19
    F          14
    G           7
    H           9
    I           3
    J           4
    CLEAN     104
========================================================
```
Output files written to `seed/data/`:
- `edge_plan.json` — full deterministic plan
- `ground_truth_v2.csv` — expected labels per record
- `MANIFEST_v2.json` — counts by scenario group and decision

After the test run also check:
- `SEED_MISMATCHES.md` — 9 engine vs label disagreements (all missing features)
- `COVERAGE.md` — per-scenario coverage table + 25 MISSING_FEATURES with fix guidance

### 5. Generate the synthetic image dataset
```
python -m seed.images
```
Expected output:
```
  Generating images for 120 collections × 6 variants …
  [ 20/120] done
  ...
  [120/120] done
  Manifest written → seed/data/images/image_manifest.csv
========================================================
EcoTrace AI — Synthetic Image Dataset Summary
========================================================
  Total images:    728
  Collections:     120
  Image size:      224×224 px
  Avg blur_score (clear): 0.76

  By variant:
    blurry            120
    clear             120
    dark              120
    duplicate           8
    near_dup          120
    overexposed       120
    rotated           120

  By category:
    IT_telecom                     171
    consumer_electronics           152
    large_appliances               140
    lighting                       103
    other                           66
    small_appliances                96
========================================================
```
Output files written to `seed/data/images/`:
- `<collection_id>_<variant>.png` — 728 procedurally drawn PNG images (224×224 px)
- `image_manifest.csv` — one row per image with:
  `collection_id, scenario, category, item_state, serial_or_imei, variant,`
  `filename, width, height, blur_score, exif_present, perceptual_hash, is_synthetic`

**Variants per collection:**

| Variant | Description | blur_score | exif_present |
|---|---|---|---|
| clear | Crisp drawing, full EXIF stub | ~0.76 | True |
| blurry | Gaussian blur radius 5 | ~0.28 | False |
| dark | Brightness 30% (poor lighting) | ~0.05 | False |
| near_dup | 3×3 noise patch (near-duplicate) | ~0.76 | True |
| overexposed | Brightness 200% (washed out) | ~0.23 | True |
| rotated | 15° rotation (partial occlusion) | ~0.76 | True |
| duplicate | Byte-identical copy (dup scenarios only) | same as clear | True |

To generate only the first N collections (faster for quick demos):
```
python -m seed.images --limit 20
```

### 6. Generate OCR ground truth dataset *(recommended next step)*

The CV pipeline needs labelled OCR output to validate `device_serial_confidence` scores.
This dataset is not yet generated — run this once `seed/ocr_ground_truth.py` is implemented:

```
python -m seed.ocr_ground_truth
```

What it will produce in `seed/data/`:
- `ocr_ground_truth.csv` — one row per image with:
  `collection_id, variant, detected_text, expected_text, confidence, correct, is_synthetic`

Why it matters: the evidence engine already consumes `device_serial_confidence` as a
signal — OCR ground truth is what a trained CV model would produce to populate that field.
Without it, the signal is hand-crafted in the seed; with it, it becomes testable against
real (or realistic) OCR output.

**Status:** not yet implemented. Listed in `COVERAGE.md` under MISSING_FEATURES.

---

### 7. Generate GPS readings dataset *(recommended next step)*

The evidence engine uses `gps_validity` but collections only store `collection_state`
(a state name), not actual coordinates. A GPS readings dataset links each collection
to a lat/lng reading and the geofence verdict.

```
python -m seed.gps_readings
```

What it will produce in `seed/data/`:
- `gps_readings.csv` — one row per collection with:
  `collection_id, scenario, facility_lat, facility_lng, geofence_radius_m,`
  `reading_lat, reading_lng, distance_m, gps_validity_signal, gps_scenario`

GPS scenarios covered:
| gps_scenario | distance_m | gps_validity_signal |
|---|---|---|
| inside_geofence | < radius | 1.0 |
| within_50m | radius < d ≤ radius+50 | 0.5 |
| outside | d > radius+50 | 0.0 |
| missing | — | 0.0 |
| spoofed | two readings 200 km apart within 10 min | 0.0 + gps_spoof flag |

Why it matters: gives the CV pipeline concrete coordinates to feed into the geofence
check that produces the `gps_validity` signal.

**Status:** not yet implemented. Listed in `COVERAGE.md` under MISSING_FEATURES.

---

### 8. Generate weight readings dataset *(optional)*

Currently weighbridge weights are embedded in `collections.csv`. A standalone dataset
makes the pipeline more explicit:

```
python -m seed.weight_readings
```

What it will produce in `seed/data/`:
- `weight_readings.csv` — one row per collection with:
  `collection_id, scale_id, declared_kg, measured_kg, deviation_pct,`
  `weight_signal, weight_source, is_synthetic`

**Status:** not yet implemented.

---

### 9. Generate narration text stubs *(Step 4 prerequisite)*

The narration engine scores a generated text narrative. Stub texts are needed before
the LLM pipeline (Step 4) is wired:

```
python -m seed.narration_stubs
```

What it will produce in `seed/data/`:
- `narration_stubs.csv` — one row per collection that reached `completion_passed`, with:
  `collection_id, scenario, narration_text, expected_narration_decision, is_synthetic`

Stubs cover clean, prompt-injection, numeric-mismatch, and stale-rule text patterns.

**Status:** not yet implemented. Prerequisite for Step 4 (LangGraph/LLM pipeline).

---

### 10. Generate edge-case images *(optional)*

The original 120 collections have images (`seed/data/images/`). The edge-case seed
(~205 records) does not. To generate images for edge-case records:

```
python -m seed.images --collections seed/data/edge_plan_collections.csv --out seed/data/images_edge
```

**Status:** edge_plan_collections.csv export not yet implemented.

---

### Start the dev server
```
uvicorn app.main:app --reload
```
Then open **http://127.0.0.1:8000/docs** in your browser.

- Click **Authorize** → register via `POST /auth/register`, login via `POST /auth/login`, paste the token
- `GET /health` — liveness probe
- `GET /progress` — step-by-step build status (Step 1 complete, Step 2 in progress)
- Full collection lifecycle: `/collections`, `/collections/{id}/evidence`, `/completion`, `/narration`
- Badge marketplace: `GET /marketplace/badges`

### Presentation cheat-sheet

| What to show | Command / URL | Status |
|---|---|---|
| All 137 tests passing | `python -m pytest -q` | ✅ ready |
| Original seed summary | `python -m seed.load --reset` | ✅ ready |
| Edge-case dataset summary | `python -m seed.load --reset --edge` | ✅ ready |
| Synthetic image dataset | `python -m seed.images` | ✅ ready |
| Live API + Swagger UI | `uvicorn app.main:app --reload` → `/docs` | ✅ ready |
| Build progress | `GET /progress` in Swagger | ✅ ready |
| Mismatches explained | open `SEED_MISMATCHES.md` | ✅ ready |
| Scenario coverage table | open `COVERAGE.md` | ✅ ready |
| OCR ground truth | `python -m seed.ocr_ground_truth` | ⏳ pending |
| GPS readings | `python -m seed.gps_readings` | ⏳ pending |
| Weight readings | `python -m seed.weight_readings` | ⏳ pending |
| Narration text stubs | `python -m seed.narration_stubs` | ⏳ pending (Step 4) |
| Edge-case images | `python -m seed.images --collections ...` | ⏳ pending |

Seed summary after `seed.load --reset` (120 collections): badge_issued 62,
completion_hold 14, evidence_rejected 36, narration_rejected 8 — matching the planned
scenario mix exactly. All seed data is synthetic, for demonstration and testing only.

## Conventions to PRESERVE in all future work

- Datetimes are **naive UTC everywhere** (`datetime.utcnow()`); request ISO strings are
  converted to naive UTC on input (tz-aware -> UTC -> drop tzinfo). Never timezone-aware.
- `app/engine/` stays pure: dataclasses in, dataclasses out. No sqlalchemy/fastapi/app.models imports.
- Weights/thresholds/windows appear as literals **ONLY** in `config.py`.
- Never use "certificate" for our output (it is a "Trust Badge").
- Evidence Trust Score and Narration Confidence stay separate; never one combined number.
- Engine receives precomputed numeric signals only — keep image/LLM logic out of the engine.

## Remaining pending work — CONTINUE HERE

Step 1 was the backend core only. The items below were explicitly OUT OF SCOPE for Step 1
and are the pending work for later steps. Add them incrementally without breaking engine
purity, the naive-UTC rule, or the two-score separation.

1. **Frontend/UI** — facilities, collections, evidence/completion/narration review,
   badge marketplace, producer obligation dashboards.
2. **Computer-vision signal pipeline** (YOLO/OCR/image processing) producing the precomputed
   numeric signals the evidence engine already consumes (device_serial_confidence,
   component_classification_confidence, image_quality, weight_consistency, etc.). CV output
   must stay numeric-only and feed the existing `EvidenceInputs`.
3. **Narration generation** (LangGraph/LLM/RAG/embeddings) to produce the narrative that the
   narration engine scores. Keep generation separate from scoring (`NarrationInputs` in,
   `NarrationResult` out).
4. **Auth** on the REST API.
5. **Docker** + **CI**.
6. **Alembic** migrations + **Postgres** deployment (models already Postgres-compatible).
7. **File upload** endpoints for evidence media and invoices.

## Verification checklist before declaring any later step done

- `python -m pytest -q` still fully green.
- `app/engine/` still imports nothing from sqlalchemy/fastapi/app.models.
- "certificate" appears nowhere; both scores still separate; datetimes still naive UTC.
- New code keeps weights/thresholds/windows in `config.py` only.

## Assumptions (Step 1)

- Create endpoints accept an optional `id` so the deterministic seed can supply pre-generated
  UUIDs; when omitted, UUID4 is generated (the "default uuid4" rule).
- Project root is the `ecotrace/` directory; run all commands from there.
