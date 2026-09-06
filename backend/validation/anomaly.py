"""
anomaly.py – Member 2: Anomaly detection across multiple records.

Detects:
  - Duplicate records (same khasra + location)
  - Area mismatch between related records for the same khasra
  - Ownership conflicts (different owners for same land parcel)
  - Unusually high number of mutations in a short time window
  - Optional: anomaly score (0.0 = normal, 1.0 = highly anomalous)
"""

from __future__ import annotations

from datetime import date, timedelta
from collections import defaultdict
from typing import Sequence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue(code: str, severity: str, message: str) -> dict:
    return {"code": code, "severity": severity, "message": message}


def _parcel_key(record: dict) -> tuple:
    """Unique key for a land parcel: (state, district, tehsil, village, khasra_number)."""
    loc = record.get("location", {})
    ld = record.get("land_details", {})
    return (
        loc.get("state", "").strip().lower(),
        loc.get("district", "").strip().lower(),
        loc.get("tehsil", "").strip().lower(),
        loc.get("village", "").strip().lower(),
        str(ld.get("khasra_number", "")).strip().lower(),
    )


def _area_in_hectares(record: dict) -> float | None:
    """Convert record area to hectares for comparison. Returns None if not possible."""
    ld = record.get("land_details", {})
    area = ld.get("area")
    unit = ld.get("area_unit", "").lower()

    if not isinstance(area, (int, float)) or area <= 0:
        return None

    CONVERSION = {
        "hectare":      1.0,
        "acre":         0.404686,
        "bigha":        0.160000,   # UP standard bigha ≈ 0.16 ha
        "square_meter": 0.0001,
        "square_feet":  0.0000929,
    }
    factor = CONVERSION.get(unit)
    return area * factor if factor else None


# ---------------------------------------------------------------------------
# Multi-record anomaly checks
# ---------------------------------------------------------------------------

def check_duplicate_records(records: list[dict]) -> list[dict]:
    """
    Flag records that share the same (location + khasra_number) and record_id.
    If record_ids differ but parcel key is identical → possible duplicate.
    """
    issues = []
    parcel_to_records: dict[tuple, list[str]] = defaultdict(list)

    for rec in records:
        key = _parcel_key(rec)
        rid = rec.get("record_id", "UNKNOWN")
        parcel_to_records[key].append(rid)

    for key, rids in parcel_to_records.items():
        if len(rids) > 1:
            issues.append(_issue(
                "DUPLICATE_RECORDS",
                "high",
                f"Multiple records found for the same land parcel "
                f"({key[0]}/{key[1]}/{key[2]}/{key[3]}, khasra={key[4]}): "
                f"record_ids {rids}."
            ))

    return issues


def check_area_mismatch(records: list[dict]) -> list[dict]:
    """
    For the same land parcel across multiple records, check that the area
    does not vary by more than AREA_TOLERANCE_PERCENT (5% by default).
    """
    AREA_TOLERANCE_PERCENT = 5.0
    issues = []
    parcel_areas: dict[tuple, list[tuple[str, float]]] = defaultdict(list)

    for rec in records:
        key = _parcel_key(rec)
        rid = rec.get("record_id", "UNKNOWN")
        area_ha = _area_in_hectares(rec)
        if area_ha:
            parcel_areas[key].append((rid, area_ha))

    for key, entries in parcel_areas.items():
        if len(entries) < 2:
            continue
        areas = [a for _, a in entries]
        min_a, max_a = min(areas), max(areas)
        if min_a == 0:
            continue
        pct_diff = (max_a - min_a) / min_a * 100
        if pct_diff > AREA_TOLERANCE_PERCENT:
            rids = [r for r, _ in entries]
            issues.append(_issue(
                "AREA_MISMATCH",
                "high",
                f"Area differs by {round(pct_diff, 1)}% across records {rids} "
                f"for khasra '{key[4]}'. Min={round(min_a, 4)} ha, Max={round(max_a, 4)} ha."
            ))

    return issues


def check_ownership_conflict(records: list[dict]) -> list[dict]:
    """
    For the same parcel, check if different records claim completely different
    owners (no common owner name at all).
    """
    issues = []
    parcel_owners: dict[tuple, list[tuple[str, set[str]]]] = defaultdict(list)

    for rec in records:
        key = _parcel_key(rec)
        rid = rec.get("record_id", "UNKNOWN")
        owners = {
            o.get("owner_name", "").strip().lower()
            for o in rec.get("ownership", [])
            if isinstance(o, dict) and o.get("owner_name")
        }
        if owners:
            parcel_owners[key].append((rid, owners))

    for key, entries in parcel_owners.items():
        if len(entries) < 2:
            continue
        # Compare consecutive records
        for i in range(len(entries) - 1):
            rid_a, owners_a = entries[i]
            rid_b, owners_b = entries[i + 1]
            common = owners_a & owners_b
            if not common:
                issues.append(_issue(
                    "OWNERSHIP_CONFLICT",
                    "high",
                    f"Records '{rid_a}' and '{rid_b}' for khasra '{key[4]}' share no common owner. "
                    f"Owners A: {sorted(owners_a)}, Owners B: {sorted(owners_b)}. "
                    "Verify mutation history."
                ))

    return issues


def check_frequent_mutations(records: list[dict]) -> list[dict]:
    """
    Flag parcels where mutations happen more than MAX_MUTATIONS_IN_WINDOW times
    within WINDOW_DAYS. High mutation frequency may indicate suspicious activity.
    """
    MAX_MUTATIONS_IN_WINDOW = 3
    WINDOW_DAYS = 365
    issues = []

    parcel_dates: dict[tuple, list[date]] = defaultdict(list)
    parcel_rids: dict[tuple, list[str]] = defaultdict(list)

    for rec in records:
        key = _parcel_key(rec)
        rid = rec.get("record_id", "UNKNOWN")
        mut = rec.get("mutation", {})
        mut_date_str = mut.get("mutation_date") if mut else None

        if mut_date_str:
            try:
                mut_date = date.fromisoformat(str(mut_date_str))
                parcel_dates[key].append(mut_date)
                parcel_rids[key].append(rid)
            except ValueError:
                pass

    for key, dates in parcel_dates.items():
        if len(dates) < MAX_MUTATIONS_IN_WINDOW:
            continue
        dates.sort()
        window = timedelta(days=WINDOW_DAYS)
        for i in range(len(dates) - MAX_MUTATIONS_IN_WINDOW + 1):
            window_dates = [d for d in dates[i:] if d <= dates[i] + window]
            if len(window_dates) >= MAX_MUTATIONS_IN_WINDOW:
                issues.append(_issue(
                    "FREQUENT_MUTATIONS",
                    "medium",
                    f"Khasra '{key[4]}' ({key[1]}/{key[3]}) has {len(window_dates)} mutations "
                    f"between {dates[i]} and {dates[i] + window}. "
                    "High mutation frequency — verify transaction history."
                ))
                break  # one issue per parcel

    return issues


# ---------------------------------------------------------------------------
# Anomaly score (single record)
# ---------------------------------------------------------------------------

SEVERITY_WEIGHTS = {"high": 1.0, "medium": 0.5, "low": 0.2}
MAX_SCORE = 10.0  # cap denominator so score stays in [0, 1]


def compute_anomaly_score(issues: list[dict]) -> float:
    """
    Returns a float in [0.0, 1.0]:
      0.0  → no issues / fully clean
      1.0  → maximum anomaly level
    """
    raw = sum(SEVERITY_WEIGHTS.get(iss.get("severity", "low"), 0.2) for iss in issues)
    return round(min(raw / MAX_SCORE, 1.0), 4)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_anomaly_checks(
    current_record: dict,
    related_records: list[dict] | None = None
) -> tuple[list[dict], float]:
    """
    Run all anomaly detection checks.

    Args:
        current_record:  The LandRecord being validated.
        related_records: Optional list of other LandRecord dicts from the database.
                         If None or empty, only single-record anomaly scoring is done.

    Returns:
        (issues_list, anomaly_score)
        - issues_list: list of issue dicts
        - anomaly_score: float in [0.0, 1.0]
    """
    all_records = [current_record] + (related_records or [])
    issues = []

    issues += check_duplicate_records(all_records)
    issues += check_area_mismatch(all_records)
    issues += check_ownership_conflict(all_records)
    issues += check_frequent_mutations(all_records)

    score = compute_anomaly_score(issues)
    return issues, score
