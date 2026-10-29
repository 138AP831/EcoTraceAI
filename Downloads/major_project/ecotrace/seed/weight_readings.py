"""Synthetic weighbridge readings dataset for EcoTrace AI.

Generates per-collection weight reading records with scale ID, declared vs
measured weight, deviation%, and the derived weight_signal used by the
evidence engine.

Weight scenarios
----------------
weighbridge_close    deviation ≤ 5%     weight_signal ~ 1.0
weighbridge_far      deviation > 5%     weight_signal = max(0, 1 - dev/0.40)
declared_only        no scale reading   weight_signal = declared × 0.85 (UNVERIFIED_WEIGHT_DISCOUNT)
missing_both         no weight at all   → raises ValueError in engine (seed marks as N/A)

Scenario assignment
-------------------
invoice_mismatch  → weighbridge_far (deviation ~15–40%)
low_quality       → weighbridge_far OR declared_only (50/50)
C10               → weighbridge_far (deviation ~40%)
C11               → declared_only
C12               → declared_only with weight=0 (validation error scenario)
All others        → weighbridge_close (deviation ~0–4%)

Output
------
seed/data/weight_readings.csv — one row per collection:
    collection_id, scenario, scale_id, declared_kg, measured_kg,
    deviation_pct, weight_signal, weight_source, is_synthetic

Usage
-----
    python -m seed.weight_readings
    python -m seed.weight_readings --limit 20
"""
from __future__ import annotations

import argparse
import csv
import os
import random
from dataclasses import dataclass
from typing import Optional

HERE     = os.path.dirname(__file__)
DATA_DIR = os.path.join(HERE, "data")
RNG_SEED = 42

UNVERIFIED_WEIGHT_DISCOUNT = 0.85   # mirrors app/config.py

_SCALES = [f"SCALE-{i:02d}" for i in range(1, 9)]

# scenario tag → weight scenario type
_TAG_TO_WGT: dict[str, str] = {
    "invoice_mismatch": "weighbridge_far",
    "low_quality":      "mixed",   # resolved per-record
    "C10":              "weighbridge_far_extreme",
    "C11":              "declared_only",
    "C12":              "declared_zero",
}


def _sig(rng: random.Random, mean: float, sd: float,
         lo: float = 0.0, hi: float = 1.0) -> float:
    return round(max(lo, min(hi, rng.gauss(mean, sd))), 4)


def _weight_signal(declared: float, measured: Optional[float],
                   source: str) -> float:
    """Compute the weight_consistency signal that the engine would receive."""
    if source == "declared_only":
        return round(declared * UNVERIFIED_WEIGHT_DISCOUNT, 4)
    if measured is None:
        return 0.0
    if declared <= 0:
        return 0.0
    deviation = abs(measured - declared) / declared
    # Signal: 1.0 at 0% dev, 0.0 at 40% dev, linear
    return round(max(0.0, 1.0 - deviation / 0.40), 4)


@dataclass
class WeightRecord:
    collection_id:  str
    scenario:       str
    scale_id:       Optional[str]
    declared_kg:    float
    measured_kg:    Optional[float]
    deviation_pct:  Optional[float]
    weight_signal:  float
    weight_source:  str        # "weighbridge" | "declared_only" | "missing" | "zero"
    is_synthetic:   bool = True


def generate_weight_readings(
    collections_csv:  str = os.path.join(DATA_DIR, "collections.csv"),
    ground_truth_csv: str = os.path.join(DATA_DIR, "ground_truth.csv"),
    out_dir:          str = DATA_DIR,
    limit:            Optional[int] = None,
    rng_seed:         int = RNG_SEED,
) -> list[WeightRecord]:
    rng = random.Random(rng_seed)
    os.makedirs(out_dir, exist_ok=True)

    scenario_map: dict[str, str] = {}
    if os.path.exists(ground_truth_csv):
        with open(ground_truth_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                scenario_map[row["collection_id"]] = row["scenario"]

    if not os.path.exists(collections_csv):
        print(f"  ⚠  collections.csv not found at {collections_csv}")
        print("  Run `python -m seed.load --reset` first.")
        return []

    records: list[WeightRecord] = []
    with open(collections_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if limit:
        rows = rows[:limit]

    for row in rows:
        cid       = row["id"]
        scenario  = scenario_map.get(cid, "unknown")
        declared  = float(row.get("declared_weight_kg") or 1.0)
        scale_id  = rng.choice(_SCALES)

        forced = _TAG_TO_WGT.get(scenario)
        if forced == "mixed":
            forced = "weighbridge_far" if rng.random() < 0.5 else "declared_only"

        wgt_type = forced or "weighbridge_close"

        measured:  Optional[float] = None
        deviation: Optional[float] = None
        source = "weighbridge"

        if wgt_type == "weighbridge_close":
            dev_pct  = abs(_sig(rng, 0.02, 0.015, 0.0, 0.04))
            sign     = rng.choice([-1, 1])
            measured = round(declared * (1 + sign * dev_pct), 3)
            deviation = round(dev_pct * 100, 2)

        elif wgt_type == "weighbridge_far":
            dev_pct  = abs(_sig(rng, 0.20, 0.08, 0.06, 0.40))
            sign     = rng.choice([-1, 1])
            measured = round(declared * (1 + sign * dev_pct), 3)
            deviation = round(dev_pct * 100, 2)

        elif wgt_type == "weighbridge_far_extreme":
            dev_pct  = abs(_sig(rng, 0.40, 0.05, 0.35, 0.50))
            sign     = rng.choice([-1, 1])
            measured = round(declared * (1 + sign * dev_pct), 3)
            deviation = round(dev_pct * 100, 2)

        elif wgt_type == "declared_only":
            scale_id = None
            measured = None
            source   = "declared_only"

        elif wgt_type == "declared_zero":
            # C12 scenario: zero weight triggers validation error in production
            declared = 0.0
            scale_id = None
            measured = None
            source   = "zero"

        signal = _weight_signal(declared, measured, source)

        records.append(WeightRecord(
            collection_id = cid,
            scenario      = scenario,
            scale_id      = scale_id,
            declared_kg   = declared,
            measured_kg   = measured,
            deviation_pct = deviation,
            weight_signal = signal,
            weight_source = source,
        ))

    _write_manifest(records, os.path.join(out_dir, "weight_readings.csv"))
    _print_summary(records)
    return records


def _write_manifest(records: list[WeightRecord], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "collection_id", "scenario", "scale_id",
            "declared_kg", "measured_kg", "deviation_pct",
            "weight_signal", "weight_source", "is_synthetic",
        ])
        for r in records:
            w.writerow([
                r.collection_id, r.scenario, r.scale_id or "",
                r.declared_kg, r.measured_kg if r.measured_kg is not None else "",
                r.deviation_pct if r.deviation_pct is not None else "",
                r.weight_signal, r.weight_source, r.is_synthetic,
            ])
    print(f"\n  Manifest written → {path}")


def _print_summary(records: list[WeightRecord]) -> None:
    by_src: dict[str, int] = {}
    for r in records:
        by_src[r.weight_source] = by_src.get(r.weight_source, 0) + 1

    wb = [r for r in records if r.deviation_pct is not None]
    avg_dev = round(sum(r.deviation_pct for r in wb) / len(wb), 2) if wb else 0
    avg_sig = round(sum(r.weight_signal for r in records) / len(records), 4) if records else 0

    print(f"\n{'='*56}")
    print(f"EcoTrace AI — Weight Readings Summary")
    print(f"{'='*56}")
    print(f"  Total records:       {len(records)}")
    print(f"  Avg deviation%:      {avg_dev}%")
    print(f"  Avg weight_signal:   {avg_sig}")
    print(f"\n  By weight source:")
    for s in sorted(by_src):
        print(f"    {s:20s}  {by_src[s]:>5}")
    print(f"{'='*56}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate weight readings dataset for EcoTrace AI.")
    parser.add_argument("--collections",
        default=os.path.join(DATA_DIR, "collections.csv"))
    parser.add_argument("--ground-truth",
        default=os.path.join(DATA_DIR, "ground_truth.csv"))
    parser.add_argument("--out", default=DATA_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=RNG_SEED)
    args = parser.parse_args()

    generate_weight_readings(
        collections_csv  = args.collections,
        ground_truth_csv = args.ground_truth,
        out_dir          = args.out,
        limit            = args.limit,
        rng_seed         = args.seed,
    )


if __name__ == "__main__":
    main()
