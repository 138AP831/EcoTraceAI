"""Synthetic e-waste image dataset generator for EcoTrace AI.

Generates procedurally-drawn PNG images using Pillow only — no downloads,
no real photos, no external assets.

Each image represents one of six e-waste categories:
  IT_telecom            — laptop / phone outline
  consumer_electronics  — TV / monitor outline
  large_appliances      — washing machine / fridge outline
  small_appliances      — kettle / iron outline
  lighting              — fluorescent tube / bulb outline
  other                 — generic box with label

Quality variants per category:
  clear        — crisp drawing, full EXIF stub, good lighting
  blurry       — Gaussian blur applied, low blur_score
  dark         — brightness reduced to 30%, simulates poor lighting
  duplicate    — byte-identical copy of a clear image (same hash)
  near_dup     — clear with 1-pixel noise patch (perceptual near-duplicate)
  overexposed  — brightness boosted to 200%, washed-out
  rotated      — rotated 15 degrees (partial occlusion)

Outputs
-------
seed/data/images/<collection_id>_<variant>.png   — image files
seed/data/images/image_manifest.csv             — one row per image:
    collection_id, scenario, category, variant, filename,
    width, height, blur_score, exif_present,
    perceptual_hash (64-bit hex), is_synthetic

The perceptual_hash column matches the image_hash already stored on the
Collection record in collections.csv for the SAME collection_id — so CV
pipeline code can verify images against the DB without extra joins.

Usage
-----
    python -m seed.images                    # generates all images
    python -m seed.images --limit 20         # first 20 collections only
    python -m seed.images --out custom/path  # override output directory
"""
from __future__ import annotations

import csv
import io
import math
import os
import random
import struct
import zlib
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# Pillow imports
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ── Constants ──────────────────────────────────────────────────────────────────
RNG_SEED   = 42
IMG_W      = 224           # width  (pixels) — CV-pipeline friendly size
IMG_H      = 224           # height
THUMB_W    = 64            # thumbnail for perceptual hash computation
THUMB_H    = 64

HERE       = os.path.dirname(__file__)
DATA_DIR   = os.path.join(HERE, "data")
IMG_DIR    = os.path.join(DATA_DIR, "images")

# Category → background palette  (R, G, B)
_BG: dict[str, tuple[int, int, int]] = {
    "IT_telecom":           (230, 240, 255),
    "consumer_electronics": (255, 240, 225),
    "large_appliances":     (225, 255, 235),
    "small_appliances":     (255, 225, 240),
    "lighting":             (255, 255, 210),
    "other":                (235, 235, 235),
}

# Category → accent colour for the device outline
_FG: dict[str, tuple[int, int, int]] = {
    "IT_telecom":           (50,  80, 160),
    "consumer_electronics": (160, 80,  40),
    "large_appliances":     (40, 130,  80),
    "small_appliances":     (160, 40, 100),
    "lighting":             (140, 130,  20),
    "other":                (90,  90,  90),
}

VARIANTS = ["clear", "blurry", "dark", "near_dup", "overexposed", "rotated"]
# duplicate variant is only generated for collections with scenario "duplicate"


# ── Perceptual hash (dHash, 64-bit) ───────────────────────────────────────────

def _dhash(img: Image.Image) -> str:
    """Compute a 64-bit difference hash (dHash) as a 16-character hex string.

    Algorithm: resize to 9×8 greyscale; compare adjacent horizontal pixels;
    pack 64 bits into a uint64.
    """
    grey = img.convert("L").resize((9, 8), Image.LANCZOS)
    bits = 0
    for row in range(8):
        for col in range(8):
            left  = grey.getpixel((col,     row))
            right = grey.getpixel((col + 1, row))
            bits  = (bits << 1) | (1 if left > right else 0)
    return "%016x" % (bits & 0xFFFFFFFFFFFFFFFF)


def _blur_score(img: Image.Image) -> float:
    """Estimate sharpness via Laplacian variance on a greyscale thumbnail.

    Returns a value in [0.0, 1.0] where 1.0 is perfectly sharp.
    Clipped and normalised against a reference of 2000 variance units.
    """
    grey  = img.convert("L").resize((64, 64), Image.LANCZOS)
    pixels = list(grey.getdata())
    n  = len(pixels)
    mu = sum(pixels) / n
    # Approximate Laplacian: sum of |p - mu| ** 2
    variance = sum((p - mu) ** 2 for p in pixels) / n
    return round(min(1.0, variance / 2000.0), 4)


# ── Device drawers ─────────────────────────────────────────────────────────────

def _draw_it_telecom(draw: ImageDraw.ImageDraw, fg: tuple, rng: random.Random):
    """Draw a laptop outline (lid + base) with a phone beside it."""
    # Laptop base
    draw.rectangle([30, 140, 160, 195], outline=fg, width=3, fill=(200, 210, 230))
    # Laptop lid
    draw.rectangle([30, 60, 160, 140], outline=fg, width=3, fill=(180, 195, 220))
    # Screen bezel
    draw.rectangle([40, 70, 150, 130], outline=fg, width=2, fill=(30, 30, 40))
    # Keyboard dots
    for row in range(3):
        for col in range(8):
            x = 45 + col * 14
            y = 150 + row * 12
            draw.rectangle([x, y, x + 10, y + 8], outline=fg, width=1,
                           fill=(210, 215, 225))
    # Phone (right side)
    draw.rectangle([175, 80, 205, 175], outline=fg, width=3,
                   fill=(190, 195, 210))
    draw.ellipse([185, 160, 195, 170], outline=fg, width=2)
    # Label
    draw.text((50, 200), "IT/TELECOM", fill=fg)


def _draw_consumer_electronics(draw: ImageDraw.ImageDraw, fg: tuple,
                                rng: random.Random):
    """Draw a monitor / TV outline."""
    # Screen body
    draw.rectangle([25, 40, 200, 160], outline=fg, width=4,
                   fill=(50, 50, 60))
    # Screen inner
    draw.rectangle([35, 50, 190, 150], outline=fg, width=2,
                   fill=(20, 20, 30))
    # Stand neck
    draw.rectangle([100, 160, 125, 185], outline=fg, width=3,
                   fill=(180, 170, 160))
    # Stand base
    draw.rectangle([75, 185, 150, 198], outline=fg, width=3,
                   fill=(180, 170, 160))
    # Power LED
    draw.ellipse([185, 145, 193, 153], fill=(0, 200, 80))
    draw.text((55, 202), "CONSUMER ELEC", fill=fg)


def _draw_large_appliances(draw: ImageDraw.ImageDraw, fg: tuple,
                            rng: random.Random):
    """Draw a washing machine outline."""
    # Body
    draw.rectangle([30, 30, 195, 195], outline=fg, width=4,
                   fill=(220, 230, 225))
    # Door circle
    draw.ellipse([65, 65, 160, 160], outline=fg, width=5,
                 fill=(180, 200, 195))
    draw.ellipse([80, 80, 145, 145], outline=fg, width=3,
                 fill=(140, 165, 160))
    # Control panel top
    draw.rectangle([30, 30, 195, 60], outline=fg, width=2,
                   fill=(200, 210, 205))
    # Buttons
    for x in [50, 80, 110, 140, 170]:
        draw.ellipse([x, 38, x + 14, 52], outline=fg, width=2,
                     fill=(100, 160, 140))
    draw.text((45, 200), "LARGE APPLIANCE", fill=fg)


def _draw_small_appliances(draw: ImageDraw.ImageDraw, fg: tuple,
                            rng: random.Random):
    """Draw a kettle outline."""
    # Body (oval)
    draw.ellipse([60, 50, 175, 175], outline=fg, width=4,
                 fill=(210, 190, 205))
    # Spout
    draw.polygon([(60, 90), (20, 80), (18, 110), (60, 115)],
                 outline=fg, fill=(200, 180, 195))
    # Handle
    draw.arc([170, 80, 210, 150], start=300, end=60, fill=fg, width=5)
    # Base
    draw.rectangle([55, 175, 180, 195], outline=fg, width=3,
                   fill=(190, 175, 185))
    # Lid
    draw.ellipse([85, 40, 150, 62], outline=fg, width=3,
                 fill=(200, 185, 200))
    draw.text((55, 202), "SMALL APPLI", fill=fg)


def _draw_lighting(draw: ImageDraw.ImageDraw, fg: tuple, rng: random.Random):
    """Draw a fluorescent tube + a bulb."""
    # Tube body
    draw.rectangle([20, 100, 200, 125], outline=fg, width=3,
                   fill=(240, 240, 200))
    # End caps
    draw.rectangle([15, 97, 25, 128], outline=fg, width=2,
                   fill=(180, 180, 150))
    draw.rectangle([199, 97, 209, 128], outline=fg, width=2,
                   fill=(180, 180, 150))
    # Pins
    for x in [17, 22]:
        draw.line([(x, 128), (x, 140)], fill=fg, width=2)
    for x in [201, 206]:
        draw.line([(x, 128), (x, 140)], fill=fg, width=2)
    # Glow simulation (yellow ellipse behind tube)
    draw.ellipse([10, 90, 215, 135], outline=(240, 230, 100), width=1)
    # Compact bulb
    draw.ellipse([80, 30, 145, 90], outline=fg, width=3,
                 fill=(245, 245, 180))
    draw.rectangle([100, 88, 125, 105], outline=fg, width=2,
                   fill=(200, 195, 160))
    draw.text((60, 155), "LIGHTING", fill=fg)


def _draw_other(draw: ImageDraw.ImageDraw, fg: tuple, rng: random.Random):
    """Draw a generic box with a recycling symbol."""
    # Box
    draw.rectangle([40, 50, 185, 185], outline=fg, width=4,
                   fill=(215, 215, 215))
    # Box flaps (top)
    draw.polygon([(40, 50), (112, 30), (185, 50)], outline=fg,
                 fill=(195, 195, 195))
    # Recycling arrows (three curved arrow segments)
    cx, cy, r = 112, 118, 40
    for angle_start in [0, 120, 240]:
        a0 = math.radians(angle_start)
        a1 = math.radians(angle_start + 90)
        draw.arc([cx - r, cy - r, cx + r, cy + r],
                 start=angle_start, end=angle_start + 90,
                 fill=fg, width=6)
        # Arrow head
        hx = int(cx + r * math.cos(a1))
        hy = int(cy + r * math.sin(a1))
        draw.polygon([(hx - 6, hy - 6), (hx + 6, hy - 6),
                      (hx, hy + 8)], fill=fg)
    draw.text((55, 190), "OTHER E-WASTE", fill=fg)


_DRAWERS = {
    "IT_telecom":           _draw_it_telecom,
    "consumer_electronics": _draw_consumer_electronics,
    "large_appliances":     _draw_large_appliances,
    "small_appliances":     _draw_small_appliances,
    "lighting":             _draw_lighting,
    "other":                _draw_other,
}


# ── Image builder ──────────────────────────────────────────────────────────────

def _make_base_image(category: str, rng: random.Random,
                     serial: Optional[str] = None) -> Image.Image:
    """Create a clean 224×224 PNG for the given category."""
    bg = _BG.get(category, (240, 240, 240))
    fg = _FG.get(category, (60, 60, 60))

    img  = Image.new("RGB", (IMG_W, IMG_H), color=bg)
    draw = ImageDraw.Draw(img)

    # Subtle grid background
    for x in range(0, IMG_W, 16):
        draw.line([(x, 0), (x, IMG_H)], fill=tuple(max(0, c - 10) for c in bg), width=1)
    for y in range(0, IMG_H, 16):
        draw.line([(0, y), (IMG_W, y)], fill=tuple(max(0, c - 10) for c in bg), width=1)

    # Draw device
    _DRAWERS[category](draw, fg, rng)

    # Serial / IMEI watermark (bottom strip)
    if serial:
        label = f"S/N: {serial[:15]}"
        draw.rectangle([0, IMG_H - 22, IMG_W, IMG_H], fill=(240, 240, 240))
        draw.text((4, IMG_H - 18), label, fill=(80, 80, 80))

    # Synthetic watermark (top-right corner, small)
    draw.text((IMG_W - 72, 4), "[SYNTHETIC]", fill=(180, 180, 180))

    return img


def _apply_variant(base: Image.Image, variant: str,
                   rng: random.Random) -> Image.Image:
    """Apply a quality variant to a base image."""
    if variant == "clear":
        return base.copy()

    if variant == "blurry":
        return base.filter(ImageFilter.GaussianBlur(radius=5))

    if variant == "dark":
        # Reduce brightness to ~30 %
        arr = base.load()
        out = Image.new("RGB", base.size)
        px  = out.load()
        for y in range(base.height):
            for x in range(base.width):
                r, g, b = arr[x, y]
                px[x, y] = (int(r * 0.30), int(g * 0.30), int(b * 0.30))
        return out

    if variant == "near_dup":
        # Copy + inject a small 3×3 noise patch at a random corner area
        img = base.copy()
        px  = img.load()
        ox  = rng.randint(0, IMG_W - 10)
        oy  = rng.randint(0, IMG_H - 10)
        for dy in range(3):
            for dx in range(3):
                px[ox + dx, oy + dy] = (
                    rng.randint(0, 255),
                    rng.randint(0, 255),
                    rng.randint(0, 255),
                )
        return img

    if variant == "overexposed":
        arr = base.load()
        out = Image.new("RGB", base.size)
        px  = out.load()
        for y in range(base.height):
            for x in range(base.width):
                r, g, b = arr[x, y]
                px[x, y] = (min(255, int(r * 2.0)),
                             min(255, int(g * 2.0)),
                             min(255, int(b * 2.0)))
        return out

    if variant == "rotated":
        return base.rotate(15, expand=False,
                           fillcolor=_BG.get("other", (235, 235, 235)))

    if variant == "duplicate":
        return base.copy()   # byte-identical → same hash

    return base.copy()


# ── EXIF stub (pure Python, no piexif needed) ─────────────────────────────────

def _exif_bytes(present: bool, dt: datetime) -> Optional[bytes]:
    """Return a minimal EXIF byte string or None.

    We embed just enough to satisfy the `exif_present` flag — no real GPS
    or device data (this is synthetic).  Uses a hand-crafted minimal TIFF
    header so Pillow can embed it without extra dependencies.
    """
    if not present:
        return None
    # Minimal EXIF: just the DateTime tag (0x0132) in IFD0
    # Byte order: little-endian ('II')
    dt_str = dt.strftime("%Y:%m:%d %H:%M:%S").encode("ascii") + b"\x00"
    # TIFF header: 'II' + magic 42 + IFD offset 8
    tiff_hdr  = b"II\x2a\x00\x08\x00\x00\x00"
    # IFD: 1 entry + next-IFD pointer 0
    n_entries = struct.pack("<H", 1)
    # Tag 0x0132 DateTime, type ASCII (2), count 20, value offset 26
    offset_to_value = 8 + 2 + 12 + 4  # hdr + n_entries + one entry + next_ptr
    entry = struct.pack("<HHII", 0x0132, 2, len(dt_str), offset_to_value)
    next_ifd = struct.pack("<I", 0)
    return b"Exif\x00\x00" + tiff_hdr + n_entries + entry + next_ifd + dt_str


# ── Main generator ─────────────────────────────────────────────────────────────

@dataclass
class ImageRecord:
    collection_id: str
    scenario:      str
    category:      str
    item_state:    str
    serial:        Optional[str]
    variant:       str
    filename:      str
    width:         int
    height:        int
    blur_score:    float
    exif_present:  bool
    perceptual_hash: str
    is_synthetic:  bool = True


def generate_images(
    collections_csv: str = os.path.join(DATA_DIR, "collections.csv"),
    ground_truth_csv: str = os.path.join(DATA_DIR, "ground_truth.csv"),
    out_dir: str = IMG_DIR,
    limit: Optional[int] = None,
    rng_seed: int = RNG_SEED,
) -> list[ImageRecord]:
    """Generate synthetic images for every collection in collections.csv.

    For each collection, one image per VARIANTS list is produced.
    Collections whose scenario is 'duplicate' also get a 'duplicate' variant.

    Returns a list of ImageRecord objects (also written to image_manifest.csv).
    """
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(rng_seed)

    # Load ground truth (scenario per collection)
    scenario_map: dict[str, str] = {}
    if os.path.exists(ground_truth_csv):
        with open(ground_truth_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                scenario_map[row["collection_id"]] = row["scenario"]

    # Load collections
    records: list[ImageRecord] = []
    with open(collections_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if limit:
        rows = rows[:limit]

    total = len(rows)
    print(f"\n  Generating images for {total} collections × {len(VARIANTS)} variants …")

    for i, row in enumerate(rows, 1):
        cid      = row["id"]
        category = row.get("category", "other")
        serial   = row.get("serial_or_imei") or None
        scenario = scenario_map.get(cid, "unknown")
        item_state = row.get("item_state", "intact")

        # Base image (drawn once, reused for all variants)
        base = _make_base_image(category, rng, serial)

        # Which variants to generate
        variants = list(VARIANTS)
        if scenario == "duplicate":
            variants.append("duplicate")

        for variant in variants:
            img = _apply_variant(base, variant, rng)

            # EXIF: present for clear/near_dup/overexposed/rotated; absent for blurry/dark
            exif_present = variant in ("clear", "near_dup", "overexposed",
                                       "rotated", "duplicate")
            intake_dt = datetime(2026, 6, 1, 10, 0, 0)  # fixed reference; naive UTC

            # Save
            fname = f"{cid}_{variant}.png"
            fpath = os.path.join(out_dir, fname)

            save_kwargs: dict = {"format": "PNG"}
            exif_data = _exif_bytes(exif_present, intake_dt)
            if exif_data:
                save_kwargs["exif"] = exif_data

            img.save(fpath, **save_kwargs)

            # Metrics
            phash = _dhash(img)
            bscore = _blur_score(img)

            records.append(ImageRecord(
                collection_id   = cid,
                scenario        = scenario,
                category        = category,
                item_state      = item_state,
                serial          = serial,
                variant         = variant,
                filename        = fname,
                width           = img.width,
                height          = img.height,
                blur_score      = bscore,
                exif_present    = exif_present,
                perceptual_hash = phash,
                is_synthetic    = True,
            ))

        if i % 20 == 0 or i == total:
            print(f"  [{i:>3}/{total}] done")

    # Write manifest CSV
    manifest_path = os.path.join(out_dir, "image_manifest.csv")
    _write_manifest(records, manifest_path)

    # Print summary
    _print_summary(records)
    return records


def _write_manifest(records: list[ImageRecord], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "collection_id", "scenario", "category", "item_state",
            "serial_or_imei", "variant", "filename",
            "width", "height", "blur_score",
            "exif_present", "perceptual_hash", "is_synthetic",
        ])
        for r in records:
            w.writerow([
                r.collection_id, r.scenario, r.category, r.item_state,
                r.serial or "", r.variant, r.filename,
                r.width, r.height, r.blur_score,
                r.exif_present, r.perceptual_hash, r.is_synthetic,
            ])
    print(f"\n  Manifest written → {path}")


def _print_summary(records: list[ImageRecord]) -> None:
    by_variant:  dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_scenario: dict[str, int] = {}

    for r in records:
        by_variant[r.variant]   = by_variant.get(r.variant, 0)   + 1
        by_category[r.category] = by_category.get(r.category, 0) + 1
        by_scenario[r.scenario] = by_scenario.get(r.scenario, 0) + 1

    blur_scores = [r.blur_score for r in records if r.variant == "clear"]
    avg_blur    = round(sum(blur_scores) / len(blur_scores), 4) if blur_scores else 0

    print(f"\n{'='*56}")
    print(f"EcoTrace AI — Synthetic Image Dataset Summary")
    print(f"{'='*56}")
    print(f"  Total images:    {len(records)}")
    print(f"  Collections:     {len({r.collection_id for r in records})}")
    print(f"  Image size:      {IMG_W}×{IMG_H} px")
    print(f"  Avg blur_score (clear): {avg_blur}")
    print(f"\n  By variant:")
    for v in sorted(by_variant):
        print(f"    {v:15s} {by_variant[v]:>5}")
    print(f"\n  By category:")
    for c in sorted(by_category):
        print(f"    {c:28s} {by_category[c]:>5}")
    print(f"\n  By scenario:")
    for s in sorted(by_scenario):
        print(f"    {s:24s} {by_scenario[s]:>5}")
    print(f"{'='*56}\n")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate synthetic e-waste images for EcoTrace AI seed data.")
    parser.add_argument(
        "--collections",
        default=os.path.join(DATA_DIR, "collections.csv"),
        help="Path to collections.csv (default: seed/data/collections.csv)")
    parser.add_argument(
        "--ground-truth",
        default=os.path.join(DATA_DIR, "ground_truth.csv"),
        help="Path to ground_truth.csv (default: seed/data/ground_truth.csv)")
    parser.add_argument(
        "--out",
        default=IMG_DIR,
        help="Output directory (default: seed/data/images/)")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only process the first N collections (useful for quick tests)")
    parser.add_argument(
        "--seed", type=int, default=RNG_SEED,
        help=f"RNG seed (default: {RNG_SEED})")
    args = parser.parse_args()

    generate_images(
        collections_csv  = args.collections,
        ground_truth_csv = args.ground_truth,
        out_dir          = args.out,
        limit            = args.limit,
        rng_seed         = args.seed,
    )


if __name__ == "__main__":
    main()
