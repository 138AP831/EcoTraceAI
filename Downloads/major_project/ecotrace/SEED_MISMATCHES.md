# SEED_MISMATCHES.md

Generated automatically by `tests/test_edge_cases.py::TestSeedIntegrity`.

**9 mismatch(es) detected.**

| scenario_tag | stage | actual | expected | detail |
|---|---|---|---|---|
| A11 | evidence_decision | VERIFIED | REVIEW | score=0.911 reason=auto_verified |
| C3 | evidence_decision | VERIFIED | REVIEW | score=0.813 reason=auto_verified |
| C4 | evidence_decision | VERIFIED | REVIEW | score=0.813 reason=auto_verified |
| C5 | evidence_decision | VERIFIED | REVIEW | score=0.963 reason=auto_verified |
| C6 | evidence_decision | VERIFIED | REVIEW | score=0.963 reason=auto_verified |
| C14 | evidence_decision | VERIFIED | REVIEW | score=0.963 reason=auto_verified |
| E14 | gate | PASS | HOLD | reasons=[] |
| E15 | gate | PASS | HOLD | reasons=[] |
| E16 | gate | PASS | HOLD | reasons=[] |

## Reasons for mismatches

Most mismatches arise from features that are specified but not yet
implemented in the current engine. These are listed in COVERAGE.md
under `MISSING_FEATURES`.

| Feature | Affected scenarios |
|---|---|
| Force-review flags (gps_spoof, timestamp_mismatch, unknown_category, wrong_facility_slip, gaming_flag, stale_rule) | A11, C3, C4, C5, C6, C14, F9, F11 |
| Packed/pre-pack state capture (state_not_captured) | A6 |
| Serial duplicate as hard gate | B5 |
| Buyer registry check | E14 |
| Invoice number uniqueness | E15 |
| Completion media hash reuse | E16 |
| Obligation ceiling (badge > remaining) | G6, G7 |
| Reliability rollups | H1-H10 |
| Picker.is_blocked field | I2 |
| lot_id, previous_record_id, offline_sync fields | A9, J1, J7 |
| Timezone-aware UTC datetimes in engine | all records |
