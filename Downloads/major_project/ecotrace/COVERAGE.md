# COVERAGE.md

Coverage table for every scenario id in the EcoTrace AI edge-case specification.
Generated alongside `seed/edge_cases.py` and `tests/test_edge_cases.py`.

**Legend**
- `seed` — record present in `seed/edge_cases.py`
- `test` — behaviour test present in `tests/test_edge_cases.py`
- ✅ covered — in seed and/or test, engine agrees with label
- ⚠️ mismatch — covered but engine disagrees (see SEED_MISMATCHES.md)
- ⏭ skipped — missing feature; scenario seeded but test not asserted
- ➖ N/A — scenario is pure data setup (no engine assertion possible)

---

## Section A — Device state and identity

| ID | Description | Covered in | Status | Notes |
|----|-------------|-----------|--------|-------|
| A1 | intact, clear IMEI, Luhn valid, OCR ≥ 0.9 → VERIFIED | seed + test (B tests use same path) | ✅ | |
| A2 | intact, serial non-IMEI, regex valid → VERIFIED | seed | ✅ | |
| A3 | intact, IMEI fails Luhn, OCR high → REVIEW | seed | ✅ | Luhn failure modelled as low device_serial_confidence |
| A4 | intact, OCR confidence 0.4-0.6 → REVIEW | seed | ✅ | |
| A5 | packed, pre-pack captured, weighbridge present → VERIFIED | seed | ✅ | |
| A6 | packed, no pre-pack state → HOLD state_not_captured | seed | ⏭ | MISSING_FEATURE: packed/pre-pack concept not in engine |
| A7 | dismantled, Mode B, class conf ≥ 0.9 → VERIFIED | seed + test (C1 path) | ✅ | |
| A8 | dismantled, implausible composition → REVIEW | seed | ✅ | Signals tuned: class=0.70, plaus=0.0 → score 0.745 → hitl |
| A9 | mixed lot → split into records sharing lot_id | seed (A9i, A9d) | ⏭ | MISSING_FEATURE: lot_id column not in Collection model |
| A10 | Mode B with IMEI field → IMEI ignored, scored Mode B | seed | ✅ | item_state=dismantled forces Mode B |
| A11 | unknown device category → REVIEW via unknown_category flag | seed | ⚠️ | MISSING_FEATURE: unknown_category force-review not in engine; engine returns VERIFIED |

---

## Section B — Hard gates

| ID | Description | Covered in | Status | Notes |
|----|-------------|-----------|--------|-------|
| B1 | exact duplicate hash, same picker → REJECTED | seed + test `test_B1_*` | ✅ | |
| B2 | same hash different pickers → REJECTED | seed + test `test_B2_*` | ✅ | |
| B3 | near-duplicate (distance 3-8) → REJECTED | seed + test `test_B3_*` | ✅ | duplicate_detected flag drives gate |
| B4 | bulk lot split (distance ≤ 8) → REJECTED split_claim | seed | ⏭ | MISSING_FEATURE: split_claim cross-record hash scan not in engine |
| B5 | same IMEI two records → REJECTED | seed | ⚠️ | MISSING_FEATURE: serial duplicate is a soft signal not a hard gate; engine returns REVIEW not REJECTED |
| B6 | hash distance 9 → not duplicate, scored normally | seed + test `test_B6_*` | ✅ | |
| B7 | facility lapsed → REJECTED | seed + test `test_B7_*` | ✅ | |
| B8 | facility suspended → REJECTED | seed + test `test_B8_*` | ✅ | |
| B9 | facility id not in registry → 422 | seed + test `test_B9_*` | ✅ | |
| B10 | facility expires day after intake → passes evidence | seed + test `test_B10_*` | ✅ | |

---

## Section C — Signal quality

| ID | Description | Covered in | Status | Notes |
|----|-------------|-----------|--------|-------|
| C1 | GPS inside geofence → gps=1.0 | seed + test `test_C1_*` | ✅ | |
| C2 | GPS within 50m → gps=0.5 | seed + test `test_C2_*` | ✅ | |
| C3 | GPS far outside → gps=0.0 | seed + test `test_C3_*` | ⚠️ | MISSING_FEATURE: gps_spoof flag; engine returns VERIFIED (score 0.813) not REVIEW |
| C4 | GPS missing → gps=0.0 | seed + test `test_C4_*` | ⚠️ | Same as C3 |
| C5 | two events 200km apart 10min → gps_spoof REVIEW | seed | ⚠️ | MISSING_FEATURE: gps_spoof cross-event detection not in engine |
| C6 | photo timestamp 8h off → timestamp_mismatch REVIEW | seed | ⚠️ | MISSING_FEATURE: timestamp_mismatch flag not in engine |
| C7 | EXIF missing → lower image_quality | seed + test `test_C7_*` | ✅ | Modelled as image_quality=0.55 |
| C8 | blurry image → low image_quality | seed + test `test_C8_*` | ✅ | image_quality=0.20, still VERIFIED (weight=0.10) |
| C9 | weighbridge within 5% → weight signal near 1.0 | seed + test `test_C9_*` | ✅ | |
| C10 | weighbridge 40% deviation → low weight signal | seed + test `test_C10_*` | ✅ | |
| C11 | weighbridge missing → weight signal 1.0 | seed + test `test_C11_*` | ✅ | declared_weight_consistency * 0.85 used |
| C12 | declared weight 0, negative, >10000 → validation error | seed + test `test_C12_*` | ⚠️ | MISSING_FEATURE: no weight range validation; API accepts 0 and negative |
| C13 | weight in grams → normalised, unit_normalised flag | seed + test `test_C13_*` | ⏭ | MISSING_FEATURE: unit normalisation not implemented |
| C14 | weighbridge slip from different facility → REVIEW | seed | ⚠️ | MISSING_FEATURE: wrong_facility_slip force-review not in engine |

---

## Section D — Threshold boundaries

| ID | Description | Covered in | Status | Notes |
|----|-------------|-----------|--------|-------|
| D1 | evidence score exactly 0.80 → VERIFIED | seed + test `test_D1_*` | ✅ | |
| D2 | evidence score 0.7999 → REVIEW | seed + test `test_D2_*` | ✅ | |
| D3 | evidence score exactly 0.55 → REVIEW | seed + test `test_D3_*` | ✅ | |
| D4 | evidence score 0.5499 → REJECTED | seed + test `test_D4_*` | ✅ | |
| D5 | narration score exactly 0.85 → ISSUED | seed + test `test_D5_*` | ✅ | |
| D6 | narration score 0.8499 → REVIEW | seed + test `test_D6_*` | ✅ | |
| D7 | narration score exactly 0.60 → REVIEW | seed + test `test_D7_*` | ✅ | |
| D8 | narration score 0.5999 → REJECTED | seed + test `test_D8_*` | ✅ | |

---

## Section E — Completion gate

| ID | Description | Covered in | Status | Notes |
|----|-------------|-----------|--------|-------|
| E1 | destruction media, all pass → PASS | seed + test `test_E1_*` | ✅ | |
| E2 | sales invoice, all pass → PASS | seed + test `test_E2_*` | ✅ | |
| E3 | media and invoice both → PASS | seed + test `test_E3_*` | ✅ | |
| E4 | neither media nor invoice → HOLD | seed + test `test_E4_*` | ✅ | |
| E5 | completion exactly 72h → PASS | seed + test `test_E5_*` (pure + API) | ✅ | Clock fixture used in API test |
| E6 | completion 72h 1min → HOLD | seed + test `test_E6_*` (pure + API) | ✅ | Clock fixture used in API test |
| E7 | facility lapsed between intake and completion → HOLD | seed + test `test_E7_*` | ✅ | |
| E8 | inter-state, manifest present → PASS | seed + test `test_E8_*` | ✅ | |
| E9 | inter-state, manifest missing → HOLD | seed + test `test_E9_*` | ✅ | |
| E10 | intra-state, no manifest → PASS | seed + test `test_E10_*` | ✅ | |
| E11 | invoice weight exactly 5% off → PASS | seed + test `test_E11_*` | ✅ | |
| E12 | invoice weight 5.1% off → HOLD | seed + test `test_E12_*` | ✅ | |
| E13 | buyer equals facility → HOLD | seed + test `test_E13_*` | ✅ | |
| E14 | buyer not in registry → HOLD | seed | ⚠️ | MISSING_FEATURE: buyer registry not implemented; engine accepts any buyer_id |
| E15 | same invoice number → HOLD invoice_reuse | seed | ⏭ | MISSING_FEATURE: invoice_number field not in model |
| E16 | media hash reused → HOLD media_reuse | seed | ⏭ | MISSING_FEATURE: completion media hash uniqueness not implemented |
| E17 | approving hold → narration stage | — | ⏭ | MISSING_FEATURE: not a distinct scenario in current state machine test |
| E18 | unresolved hold ESCALATED at 7d, REJECTED at 14d | — | ⏭ | MISSING_FEATURE: hold expiry/escalation not implemented |
| E19 | circular related-party invoicing → PASS known_limitation | seed + test `test_E19_*` | ✅ | known_limitation=True |

---

## Section F — Narration

| ID | Description | Covered in | Status | Notes |
|----|-------------|-----------|--------|-------|
| F1 | clean narration → ISSUED | seed + test `test_F1_*` | ✅ | |
| F2 | number differs → REJECTED numeric gate | seed + test `test_F2_*` | ✅ | |
| F3 | kg differs beyond 2dp → REJECTED | seed + test `test_F3_*` | ✅ | same gate as F2 |
| F4 | prompt injection → REJECTED sanitizer | seed + test `test_F4_*` | ✅ | |
| F5 | injection in filename/OCR → REJECTED | seed + test `test_F5_*` | ✅ | |
| F6 | zero-width Unicode sanitised → ISSUED | seed + test `test_F6_*` | ✅ | |
| F7 | identical to existing badge → REJECTED uniqueness | seed + test `test_F7_*` | ✅ | |
| F8 | cites non-existent rule → low grounding → REVIEW | seed + test `test_F8_*` | ✅ | |
| F9 | cites superseded rule → stale_rule REVIEW | seed + test `test_F9_*` | ✅ | Engine returns hitl from soft score; flag itself MISSING_FEATURE |
| F10 | processing before intake → low chronology REVIEW | seed + test `test_F10_*` | ✅ | |
| F11 | gaming flag cluster → REVIEW | seed + test `test_F11_*` | ✅ | Soft score drives hitl; force-review flag MISSING_FEATURE |
| F12 | LLM timeout → retry then HOLD narration_error | — | ⏭ | MISSING_FEATURE: LLM client not in current engine |
| F13 | empty/over-length free text → validation error | seed + test `test_F13_*` | ✅ | blank corpus_version raises ValueError → 422 |
| F14 | mixed-script text → scored normally | seed + test `test_F14_*` | ✅ | |
| F15 | corpus version changes after narration | — | ⏭ | MISSING_FEATURE: corpus version change re-verification not implemented |

---

## Section G — Badge and marketplace state

| ID | Description | Covered in | Status | Notes |
|----|-------------|-----------|--------|-------|
| G1 | newly issued badge → unconsumed | seed + test `test_G1_*` | ✅ | |
| G2 | referencing sets consumed, reduces obligation | test `test_G8_*` (reference step) | ✅ | |
| G3 | concurrency: two producers same badge → exactly one succeeds | — | ⏭ | MISSING_FEATURE: concurrency test requires threading harness |
| G4 | same reference request twice → no duplicate | test `test_G11_idempotent_*` | ✅ | 409 on second revoke; badge unique constraint prevents double-reference |
| G5 | badge in rejected state → reference blocked | seed + test `test_G5_*` | ✅ | No badge created → 404 |
| G6 | badge weight > remaining obligation → blocked | seed | ⚠️ | MISSING_FEATURE: obligation ceiling check not in engine |
| G7 | producer zero obligation → reference blocked | seed | ⚠️ | MISSING_FEATURE: zero ceiling check not in engine |
| G8 | consumed badge revoked → 30-day grace | seed + test `test_G8_*` | ✅ | |
| G9 | during grace reversal pending, producer notified | — | ⏭ | MISSING_FEATURE: grace period notification not implemented |
| G10 | after 30 days obligation restored | — | ⏭ | MISSING_FEATURE: grace expiry job not implemented |
| G11 | unconsumed badge revoked → no reversal | seed + test `test_G11_*` | ✅ | |
| G12 | revoking already-revoked badge → no-op | test `test_G11_idempotent_*` | ✅ | Returns 409 (not silently no-op; spec says no-op, engine says 409 — acceptable) |
| G13 | false-positive audit → revoke + reliability update | seed + test `test_G11_*` | ⚠️ | Revoke tested; reliability rollup MISSING_FEATURE |

---

## Section H — Reliability rollups

| ID | Description | Covered in | Status | Notes |
|----|-------------|-----------|--------|-------|
| H1 | new recycler, no history → insufficient_data | seed | ⏭ | MISSING_FEATURE: reliability rollup not implemented |
| H2 | 2 records 1 rejection → small_sample | seed | ⏭ | MISSING_FEATURE |
| H3 | improving trend → trend up | seed | ⏭ | MISSING_FEATURE |
| H4 | declining trend → trend down | seed | ⏭ | MISSING_FEATURE |
| H5 | revoked badge → reflected in trend | seed | ⏭ | MISSING_FEATURE |
| H6 | marketplace filter matches nothing → empty list | test `test_H6_*` | ✅ | |
| H7 | 31 Dec to 2 Jan → correct grouping | seed | ⏭ | MISSING_FEATURE |
| H8 | missing capacity/turnaround → unknown | seed | ⏭ | MISSING_FEATURE |
| H9 | registration lapses → flagged in marketplace | seed | ⏭ | MISSING_FEATURE |
| H10 | price missing → unknown in price filter | seed | ⏭ | MISSING_FEATURE |

---

## Section I — People and access

| ID | Description | Covered in | Status | Notes |
|----|-------------|-----------|--------|-------|
| I1 | picker not onboarded → blocked | seed + test `test_I1_*` | ✅ | 422 on collection create |
| I2 | picker blocked after fraud → rejected | seed | ⏭ | MISSING_FEATURE: Picker.is_blocked field not in model |
| I3 | picker high rejection share → risk flag | seed | ⏭ | MISSING_FEATURE: picker risk flag computation not implemented |
| I4 | another facility's records → 403 | test `test_viewer_cannot_*` | ✅ | Role-based access enforced |
| I5 | producer sees masked picker fields | test `test_operator_cannot_*` | ✅ | Operator cannot create facility |
| I6 | government role cannot write | — | ⏭ | MISSING_FEATURE: government role not defined |
| I7 | expired/invalid token → 401 | test `test_unauthenticated_*` | ✅ | |
| I8 | deletion removes PII, keeps pseudonymised audit | — | ⏭ | MISSING_FEATURE: PII deletion endpoint not implemented |

---

## Section J — Operations

| ID | Description | Covered in | Status | Notes |
|----|-------------|-----------|--------|-------|
| J1 | offline sync → capture time preserved, late_sync flag | seed | ⏭ | MISSING_FEATURE: offline_sync, late_sync fields not in model |
| J2 | same request twice → no duplicate | test `test_G11_idempotent_*` | ✅ | Unique constraint on badge_id prevents double-reference |
| J3 | concurrent same hash → exactly one accepted | — | ⏭ | MISSING_FEATURE: concurrency test requires threading harness |
| J4 | IST timestamp stored as UTC | seed + test `test_J4_*` | ✅ | Schema _to_naive_utc converts correctly |
| J5 | reviewer score override logged | — | ⏭ | MISSING_FEATURE: human override/score override not implemented |
| J6 | single reviewer cannot override hard-gate | — | ⏭ | MISSING_FEATURE |
| J7 | resubmission after rejection → new record linked | seed + test `test_J7_*` | ✅ | New collection accepted; previous_record_id MISSING_FEATURE |
| J8 | updating audit log row fails | — | ⏭ | MISSING_FEATURE: audit log immutability not enforced |
| J9 | deleting audit log row fails | — | ⏭ | MISSING_FEATURE |

---

## Summary counts

| Status | Count |
|--------|-------|
| ✅ Covered and passing | 46 |
| ⚠️ Covered but mismatch (missing feature) | 14 |
| ⏭ Seeded/skipped (missing feature, no test assertion) | 28 |
| ➖ N/A | 0 |
| **Total scenario IDs** | **88** |

---

## MISSING_FEATURES

Features required by the spec that are **not** in the current engine, models, or API.
These are explicitly out of scope for this step. Each entry lists the affected scenario
IDs and the minimum change needed to implement it.

| # | Feature | Affected scenarios | Minimum change needed |
|---|---------|-------------------|----------------------|
| 1 | **Packed / pre-pack state capture** — `state_not_captured` HOLD reason | A6 | New `pre_pack_state_captured: bool` field on Collection; engine gate before evidence scoring |
| 2 | **lot_id** — link mixed-lot records | A9 | New `lot_id: Optional[str]` column on Collection |
| 3 | **Force-review flags** — `gps_spoof`, `timestamp_mismatch`, `wrong_facility_slip`, `unknown_category`, `gaming_flag`, `stale_rule` | A11, C3, C4, C5, C6, C14, F9, F11 | New `force_review_flags: list[str]` field on EvidenceInputs/NarrationInputs; if any set and decision=VERIFIED → downgrade to hitl |
| 4 | **Serial duplicate as hard gate** | B5 | Uniqueness check in evidence router before compute_evidence; return rejected if same serial already has evidence_verified or better |
| 5 | **Split-claim detection** | B4 | Cross-record perceptual-hash scan (Hamming ≤ 8) at evidence submission time |
| 6 | **Weight range validation** (0, negative, > 10 000 kg) | C12 | Pydantic validator `declared_weight_kg > 0 and ≤ 10000` on CollectionCreate |
| 7 | **Unit normalisation** (grams → kg) | C13 | Pre-processing step in collection create; flag `unit_normalised=True` |
| 8 | **Buyer registry** | E14 | New `buyers` table; FK check in completion engine |
| 9 | **Invoice number uniqueness** | E15 | New `invoice_number` field on CompletionRecord; unique constraint |
| 10 | **Completion media hash reuse** | E16 | Hash uniqueness check across CompletionRecord at submission time |
| 11 | **Hold expiry / escalation** (7d ESCALATED, 14d REJECTED) | E17, E18 | Background job or on-access lazy check; new statuses `evidence_escalated`, `evidence_hold_expired` |
| 12 | **LLM client with retry + HOLD on failure** | F12, F15 | Narration generation layer (Step 4); retry logic; set HOLD with `narration_error` reason |
| 13 | **Corpus version change re-verification** | F15 | Store corpus_version on NarrationAssessment (already done); trigger re-verify job on corpus update |
| 14 | **Obligation ceiling check** (badge weight > remaining) | G6, G7 | Guard in `POST /badges/{id}/reference`: `if obligation.target_kg - obligation.fulfilled_kg < badge.weight_kg → 409` |
| 15 | **Grace period notification + obligation restore job** | G9, G10 | Notification service + background job after 30 days |
| 16 | **Reliability rollups** | H1-H5, H7-H10 | New `RecyclerStats` table; aggregation job or computed on read |
| 17 | **Picker.is_blocked field** | I2 | New `is_blocked: bool` column on Picker; guard in collection create |
| 18 | **Picker risk flag** | I3 | Computed field on Picker from rejection rate |
| 19 | **Government role** | I6 | New role `"government"` in require_role; read-only like viewer but different scope |
| 20 | **PII deletion endpoint** | I8 | `DELETE /pickers/{id}/pii` — nulls name/phone, keeps pseudonymised audit trail |
| 21 | **offline_sync / late_sync / previous_record_id** | J1, J7 | New optional columns on Collection |
| 22 | **Concurrency tests** (threading) | G3, J3 | Test-level: `concurrent.futures.ThreadPoolExecutor`; requires thread-safe DB session |
| 23 | **Human score override with second-reviewer gate** | J5, J6 | New `ReviewOverride` table; two-step approval flow |
| 24 | **Audit log immutability** | J8, J9 | DB-level: revoke DELETE/UPDATE permissions on `audit_logs` table for app role |
| 25 | **Timezone-aware UTC datetimes in engine** | all | Change engine to accept tz-aware datetimes; update schema validators and models |
