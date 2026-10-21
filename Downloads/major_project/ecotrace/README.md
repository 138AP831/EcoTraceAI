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

## Run / test (from the `ecotrace/` directory)

```
pip install -r requirements.txt
python -m seed.generate            # writes plan.json, MANIFEST.json, ground_truth.csv
python -m seed.load --reset         # drop+recreate dev DB, load via API, export CSVs, print summary
python -m pytest -q                 # full suite
uvicorn app.main:app --reload       # dev server (run manually)
```

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
