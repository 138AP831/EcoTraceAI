"""Synthetic GPS readings dataset for EcoTrace AI.

For each collection in collections.csv, generates a GPS reading record
with a realistic lat/lng pair and the derived gps_validity signal used
by the evidence engine.

GPS scenarios (one per collection, deterministically assigned)
--------------------------------------------------------------
inside_geofence   distance < radius              gps_validity = 1.0
within_50m        radius < d ≤ radius + 50 m     gps_validity = 0.5
outside           d > radius + 50 m              gps_validity = 0.0
missing           no reading                     gps_validity = 0.0
spoofed           two readings ≥ 200 km apart     gps_validity = 0.0
                  within 10 minutes (flag set)

Scenario assignment follows the collection's seed scenario tag:
  duplicate, facility_lapsed, low_quality  → outside (20%) or inside (80%)
  late_completion, missing_manifest        → inside_geofence (clean)
  EDGE CASES C3                            → outside
  EDGE CASES C4                            → missing
  EDGE CASES C5                            → spoofed
  All others                               → inside_geofence

Output
------
seed/data/gps_readings.csv — one row per collection:
    collection_id, scenario, facility_lat, facility_lng,
    geofence_radius_m, reading_lat, reading_lng, distance_m,
    gps_validity_signal, gps_scenario, gps_spoof_flag, is_synthetic

Usage
-----
    python -m seed.gps_readings
    python -m seed.gps_readings --limit 20
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import random
from dataclasses import dataclass
from typing import Optional

HERE     = os.path.dirname(__file__)
DATA_DIR = os.path.join(HERE, "data")
RNG_SEED = 42

EARTH_RADIUS_M = 6_371_000.0


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lng points in metres."""
    r  = EARTH_RADIUS_M
    p  = math.pi / 180
    a  = (math.sin((lat2 - lat1) * p / 2) ** 2
          + math.cos(lat1 * p) * math.cos(lat2 * p)
          * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def _offset_point(lat: float, lng: float,
                  distance_m: float, bearing_deg: float) -> tuple[float, float]:
    """Return (lat, lng) displaced by distance_m at bearing_deg from origin."""
    R = EARTH_RADIUS_M
    d = distance_m / R
    b = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lng1 = math.radians(lng)
    lat2 = math.asin(math.sin(lat1) * math.cos(d)
                     + math.cos(lat1) * math.sin(d) * math.cos(b))
    lng2 = lng1 + math.atan2(
        math.sin(b) * math.sin(d) * math.cos(lat1),
        math.cos(d) - math.sin(lat1) * math.sin(lat2),
    )
    return round(math.degrees(lat2), 6), round(math.degrees(lng2), 6)


def _gps_validity(distance_m: float, radius_m: float, missing: bool, spoof: bool) -> float:
    if missing or spoof:
        return 0.0
    if distance_m <= radius_m:
        return 1.0
    if distance_m <= radius_m + 50:
        return 0.5
    return 0.0


# Scenario tag → which GPS scenario to apply
_TAG_TO_GPS: dict[str, str] = {
    "C3":          "outside",
    "C4":          "missing",
    "C5":          "spoofed",
    "low_quality": "outside",
    "duplicate":   "outside",
}
# All other tags → probabilistic: 90% inside, 8% within_50m, 2% outside


@dataclass
class GpsRecord:
    collection_id:      str
    scenario:           str
    facility_lat:       Optional[float]
    facility_lng:       Optional[float]
    geofence_radius_m:  Optional[float]
    reading_lat:        Optional[float]
    reading_lng:        Optional[float]
    second_lat:         Optional[float]   # for spoof scenario
    second_lng:         Optional[float]
    distance_m:         Optional[float]
    gps_validity_signal: float
    gps_scenario:       str
    gps_spoof_flag:     bool
    is_synthetic:       bool = True


def generate_gps_readings(
    collections_csv:  str = os.path.join(DATA_DIR, "collections.csv"),
    facilities_csv:   str = os.path.join(DATA_DIR, "facilities.csv"),
    ground_truth_csv: str = os.path.join(DATA_DIR, "ground_truth.csv"),
    out_dir:          str = DATA_DIR,
    limit:            Optional[int] = None,
    rng_seed:         int = RNG_SEED,
) -> list[GpsRecord]:
    rng = random.Random(rng_seed)
    os.makedirs(out_dir, exist_ok=True)

    # Load scenario map
    scenario_map: dict[str, str] = {}
    if os.path.exists(ground_truth_csv):
        with open(ground_truth_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                scenario_map[row["collection_id"]] = row["scenario"]

    # Load facility geofences
    facility_geo: dict[str, dict] = {}
    if os.path.exists(facilities_csv):
        with open(facilities_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                facility_geo[row["id"]] = {
                    "lat":    float(row["geofence_lat"]) if row.get("geofence_lat") else 17.5,
                    "lng":    float(row["geofence_lng"]) if row.get("geofence_lng") else 78.3,
                    "radius": float(row["geofence_radius_m"]) if row.get("geofence_radius_m") else 200.0,
                }

    if not os.path.exists(collections_csv):
        print(f"  ⚠  collections.csv not found at {collections_csv}")
        print("  Run `python -m seed.load --reset` first.")
        return []

    records: list[GpsRecord] = []
    with open(collections_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if limit:
        rows = rows[:limit]

    for row in rows:
        cid      = row["id"]
        fac_id   = row.get("facility_id", "")
        scenario = scenario_map.get(cid, "unknown")
        geo      = facility_geo.get(fac_id, {"lat": 17.5, "lng": 78.3, "radius": 200.0})

        f_lat    = geo["lat"]
        f_lng    = geo["lng"]
        radius   = geo["radius"]

        # Determine GPS scenario
        forced = _TAG_TO_GPS.get(scenario)
        if forced:
            gps_scenario = forced
        else:
            p = rng.random()
            if p < 0.88:
                gps_scenario = "inside_geofence"
            elif p < 0.95:
                gps_scenario = "within_50m"
            else:
                gps_scenario = "outside"

        spoof   = False
        missing = (gps_scenario == "missing")
        r_lat   = None
        r_lng   = None
        s_lat   = None
        s_lng   = None
        dist    = None

        if gps_scenario == "missing":
            pass   # all None

        elif gps_scenario == "spoofed":
            # First reading: inside geofence
            bearing  = rng.uniform(0, 360)
            dist_in  = rng.uniform(0, radius * 0.8)
            r_lat, r_lng = _offset_point(f_lat, f_lng, dist_in, bearing)
            # Second reading: 200+ km away (impossible within 10 min)
            far_bearing = rng.uniform(0, 360)
            s_lat, s_lng = _offset_point(f_lat, f_lng,
                                          rng.uniform(200_000, 400_000),
                                          far_bearing)
            dist  = round(_haversine(f_lat, f_lng, r_lat, r_lng), 2)
            spoof = True

        elif gps_scenario == "inside_geofence":
            bearing  = rng.uniform(0, 360)
            dist_m   = rng.uniform(0, radius * 0.85)
            r_lat, r_lng = _offset_point(f_lat, f_lng, dist_m, bearing)
            dist  = round(_haversine(f_lat, f_lng, r_lat, r_lng), 2)

        elif gps_scenario == "within_50m":
            bearing = rng.uniform(0, 360)
            dist_m  = radius + rng.uniform(5, 45)
            r_lat, r_lng = _offset_point(f_lat, f_lng, dist_m, bearing)
            dist  = round(_haversine(f_lat, f_lng, r_lat, r_lng), 2)

        elif gps_scenario == "outside":
            bearing = rng.uniform(0, 360)
            dist_m  = radius + rng.uniform(100, 2000)
            r_lat, r_lng = _offset_point(f_lat, f_lng, dist_m, bearing)
            dist  = round(_haversine(f_lat, f_lng, r_lat, r_lng), 2)

        validity = _gps_validity(dist or 0, radius, missing, spoof)

        records.append(GpsRecord(
            collection_id       = cid,
            scenario            = scenario,
            facility_lat        = f_lat,
            facility_lng        = f_lng,
            geofence_radius_m   = radius,
            reading_lat         = r_lat,
            reading_lng         = r_lng,
            second_lat          = s_lat,
            second_lng          = s_lng,
            distance_m          = dist,
            gps_validity_signal = validity,
            gps_scenario        = gps_scenario,
            gps_spoof_flag      = spoof,
        ))

    _write_manifest(records, os.path.join(out_dir, "gps_readings.csv"))
    _print_summary(records)
    return records


def _write_manifest(records: list[GpsRecord], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "collection_id", "scenario",
            "facility_lat", "facility_lng", "geofence_radius_m",
            "reading_lat", "reading_lng",
            "second_lat", "second_lng",
            "distance_m", "gps_validity_signal",
            "gps_scenario", "gps_spoof_flag", "is_synthetic",
        ])
        for r in records:
            w.writerow([
                r.collection_id, r.scenario,
                r.facility_lat, r.facility_lng, r.geofence_radius_m,
                r.reading_lat or "", r.reading_lng or "",
                r.second_lat or "", r.second_lng or "",
                r.distance_m or "", r.gps_validity_signal,
                r.gps_scenario, r.gps_spoof_flag, r.is_synthetic,
            ])
    print(f"\n  Manifest written → {path}")


def _print_summary(records: list[GpsRecord]) -> None:
    by_gps: dict[str, int] = {}
    for r in records:
        by_gps[r.gps_scenario] = by_gps.get(r.gps_scenario, 0) + 1

    avg_val = (round(sum(r.gps_validity_signal for r in records) / len(records), 4)
               if records else 0)

    print(f"\n{'='*56}")
    print(f"EcoTrace AI — GPS Readings Summary")
    print(f"{'='*56}")
    print(f"  Total records:       {len(records)}")
    print(f"  Avg gps_validity:    {avg_val}")
    print(f"\n  By GPS scenario:")
    for s in sorted(by_gps):
        print(f"    {s:20s}  {by_gps[s]:>5}")
    print(f"{'='*56}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate GPS readings dataset for EcoTrace AI.")
    parser.add_argument("--collections",
        default=os.path.join(DATA_DIR, "collections.csv"))
    parser.add_argument("--facilities",
        default=os.path.join(DATA_DIR, "facilities.csv"))
    parser.add_argument("--ground-truth",
        default=os.path.join(DATA_DIR, "ground_truth.csv"))
    parser.add_argument("--out", default=DATA_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=RNG_SEED)
    args = parser.parse_args()

    generate_gps_readings(
        collections_csv  = args.collections,
        facilities_csv   = args.facilities,
        ground_truth_csv = args.ground_truth,
        out_dir          = args.out,
        limit            = args.limit,
        rng_seed         = args.seed,
    )


if __name__ == "__main__":
    main()
