"""Synthetic OCR ground truth dataset for EcoTrace AI.

Generates per-image OCR output that mimics what a real OCR model would produce
when reading device serial numbers / IMEI strings from the synthetic images.

Output
------
seed/data/ocr_ground_truth.csv — one row per image with:
    collection_id, variant, expected_text, detected_text,
    confidence, correct, error_type, is_synthetic

The ``confidence`` field is what would populate ``device_serial_confidence``
in an EvidenceRequest for an intact-item collection.

Variant → confidence profile
-----------------------------
clear        confidence ~ N(0.92, 0.03)   correct = True
near_dup     confidence ~ N(0.90, 0.04)   correct = True  (tiny patch, OCR unaffected)
overexposed  confidence ~ N(0.60, 0.08)   correct = True  (washed out, harder)
rotated      confidence ~ N(0.75, 0.06)   correct = True  (rotation adds noise)
blurry       confidence ~ N(0.35, 0.10)   correct = False (blur destroys text)
dark         confidence ~ N(0.20, 0.08)   correct = False (too dark to read)
duplicate    confidence ~ N(0.92, 0.03)   correct = True  (identical to clear)

Error types when correct=False
-------------------------------
  low_contrast  — dark variant, confidence < 0.30
  blur_artifact — blurry variant, confidence < 0.50
  partial_read  — one or more characters substituted
  no_text       — confidence < 0.10, empty detected_text

Usage
-----
    python -m seed.ocr_ground_truth
    python -m seed.ocr_ground_truth --limit 20
    python -m seed.ocr_ground_truth --out custom/path
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
IMG_DIR  = os.path.join(DATA_DIR, "images")
RNG_SEED = 42

# Variant → (mean_conf, std_conf, typically_correct)
_VARIANT_PROFILE: dict[str, tuple[float, float, bool]] = {
    "clear":       (0.92, 0.03, True),
    "near_dup":    (0.90, 0.04, True),
    "overexposed": (0.60, 0.08, True),
    "rotated":     (0.75, 0.06, True),
    "blurry":      (0.35, 0.10, False),
    "dark":        (0.20, 0.08, False),
    "duplicate":   (0.92, 0.03, True),
}

# Characters that OCR commonly confuses
_OCR_SUBSTITUTIONS: dict[str, str] = {
    "0": "O", "O": "0", "1": "I", "I": "1",
    "5": "S", "S": "5", "8": "B", "B": "8",
    "G": "6", "6": "G",
}


def _sig(rng: random.Random, mean: float, sd: float) -> float:
    """Gaussian-clipped float in [0, 1] rounded to 4 dp."""
    return round(max(0.0, min(1.0, rng.gauss(mean, sd))), 4)


def _corrupt_text(text: str, rng: random.Random, n_errors: int = 2) -> str:
    """Introduce n_errors character substitutions into text."""
    if not text:
        return text
    chars = list(text)
    positions = rng.sample(range(len(chars)), min(n_errors, len(chars)))
    for pos in positions:
        c = chars[pos]
        chars[pos] = _OCR_SUBSTITUTIONS.get(c, str(rng.randint(0, 9)))
    return "".join(chars)


def _error_type(variant: str, confidence: float) -> str:
    if confidence < 0.10:
        return "no_text"
    if variant == "dark":
        return "low_contrast"
    if variant == "blurry":
        return "blur_artifact"
    return "partial_read"


@dataclass
class OcrRecord:
    collection_id:  str
    scenario:       str
    item_state:     str
    variant:        str
    expected_text:  str
    detected_text:  str
    confidence:     float
    correct:        bool
    error_type:     Optional[str]
    is_synthetic:   bool = True


def generate_ocr_ground_truth(
    collections_csv:  str = os.path.join(DATA_DIR, "collections.csv"),
    ground_truth_csv: str = os.path.join(DATA_DIR, "ground_truth.csv"),
    image_manifest:   str = os.path.join(IMG_DIR, "image_manifest.csv"),
    out_dir:          str = DATA_DIR,
    limit:            Optional[int] = None,
    rng_seed:         int = RNG_SEED,
) -> list[OcrRecord]:
    """Generate OCR ground truth for all images in the image manifest.

    Only intact-item collections have a meaningful serial/IMEI to OCR.
    Dismantled collections get a placeholder (component label string).
    """
    rng = random.Random(rng_seed)
    os.makedirs(out_dir, exist_ok=True)

    # Load scenario map
    scenario_map: dict[str, str] = {}
    if os.path.exists(ground_truth_csv):
        with open(ground_truth_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                scenario_map[row["collection_id"]] = row["scenario"]

    # Load collections: serial_or_imei and item_state
    collection_meta: dict[str, dict] = {}
    if os.path.exists(collections_csv):
        with open(collections_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                collection_meta[row["id"]] = {
                    "serial":     row.get("serial_or_imei") or "",
                    "item_state": row.get("item_state", "intact"),
                }

    # Load image manifest to get (collection_id, variant) pairs
    if not os.path.exists(image_manifest):
        print(f"  ⚠  Image manifest not found at {image_manifest}")
        print("  Run `python -m seed.images` first, then retry.")
        return []

    records: list[OcrRecord] = []
    with open(image_manifest, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if limit:
        rows = rows[:limit]

    # Filter: only rows with a variant in our profile
    rows = [r for r in rows if r["variant"] in _VARIANT_PROFILE]

    for row in rows:
        cid     = row["collection_id"]
        variant = row["variant"]
        meta    = collection_meta.get(cid, {"serial": "", "item_state": "intact"})
        serial  = meta["serial"] or "UNKNOWN"
        state   = meta["item_state"]
        scenario = scenario_map.get(cid, "unknown")

        mean_c, std_c, typically_correct = _VARIANT_PROFILE[variant]

        # Dismantled: OCR returns the component label (low confidence — no serial present)
        if state == "dismantled":
            confidence = _sig(rng, 0.30, 0.10)
            detected   = "[COMPONENT — NO SERIAL]" if confidence > 0.15 else ""
            correct    = False
            etype      = "no_serial_dismantled"
        else:
            confidence = _sig(rng, mean_c, std_c)
            correct    = typically_correct and confidence >= 0.50

            if correct:
                detected = serial
                etype    = None
            else:
                if confidence < 0.10:
                    detected = ""
                    etype    = "no_text"
                else:
                    n_err    = 1 if confidence > 0.40 else 3
                    detected = _corrupt_text(serial, rng, n_errors=n_err)
                    etype    = _error_type(variant, confidence)

        records.append(OcrRecord(
            collection_id = cid,
            scenario      = scenario,
            item_state    = state,
            variant       = variant,
            expected_text = serial if state == "intact" else "",
            detected_text = detected,
            confidence    = confidence,
            correct       = correct,
            error_type    = etype,
        ))

    _write_manifest(records, os.path.join(out_dir, "ocr_ground_truth.csv"))
    _print_summary(records)
    return records


def _write_manifest(records: list[OcrRecord], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "collection_id", "scenario", "item_state", "variant",
            "expected_text", "detected_text",
            "confidence", "correct", "error_type", "is_synthetic",
        ])
        for r in records:
            w.writerow([
                r.collection_id, r.scenario, r.item_state, r.variant,
                r.expected_text, r.detected_text,
                r.confidence, r.correct, r.error_type or "", r.is_synthetic,
            ])
    print(f"\n  Manifest written → {path}")


def _print_summary(records: list[OcrRecord]) -> None:
    total   = len(records)
    correct = sum(1 for r in records if r.correct)
    by_var: dict[str, dict[str, int]] = {}
    for r in records:
        v = r.variant
        if v not in by_var:
            by_var[v] = {"total": 0, "correct": 0}
        by_var[v]["total"]   += 1
        by_var[v]["correct"] += int(r.correct)

    avg_conf = round(sum(r.confidence for r in records) / total, 4) if total else 0

    print(f"\n{'='*56}")
    print(f"EcoTrace AI — OCR Ground Truth Summary")
    print(f"{'='*56}")
    print(f"  Total records:   {total}")
    print(f"  Correct reads:   {correct} ({100*correct//max(total,1)}%)")
    print(f"  Avg confidence:  {avg_conf}")
    print(f"\n  By variant (correct/total):")
    for v in sorted(by_var):
        d = by_var[v]
        print(f"    {v:15s}  {d['correct']:>4}/{d['total']:<4}")
    print(f"{'='*56}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate OCR ground truth for EcoTrace AI synthetic images.")
    parser.add_argument("--collections",
        default=os.path.join(DATA_DIR, "collections.csv"))
    parser.add_argument("--ground-truth",
        default=os.path.join(DATA_DIR, "ground_truth.csv"))
    parser.add_argument("--image-manifest",
        default=os.path.join(IMG_DIR, "image_manifest.csv"))
    parser.add_argument("--out", default=DATA_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=RNG_SEED)
    args = parser.parse_args()

    generate_ocr_ground_truth(
        collections_csv  = args.collections,
        ground_truth_csv = args.ground_truth,
        image_manifest   = args.image_manifest,
        out_dir          = args.out,
        limit            = args.limit,
        rng_seed         = args.seed,
    )


if __name__ == "__main__":
    main()
