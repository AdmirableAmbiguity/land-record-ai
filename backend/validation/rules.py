"""
rules.py – Member 2: Field-level validation rules.

Checks each field in a LandRecord JSON for:
  - Presence (required fields)
  - Correct data type
  - Acceptable value ranges / allowed values
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_TOP_LEVEL = ["record_id", "source_document", "location", "land_details", "ownership"]

ALLOWED_LAND_TYPES = {"agricultural", "residential", "commercial", "forest",
                      "industrial", "wasteland", "government", "other"}

ALLOWED_MUTATION_TYPES = {"sale", "inheritance", "gift", "partition", "court_order", "other"}

ALLOWED_AREA_UNITS = {"hectare", "acre", "bigha", "square_meter", "square_feet"}

MAX_AREA = {
    "hectare":       50_000,
    "acre":          123_553,
    "bigha":         500_000,
    "square_meter":  500_000_000,
    "square_feet":   5_382_000_000,
}

MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue(code: str, severity: str, message: str) -> dict:
    """Return a single issue dict in the standard format."""
    return {"code": code, "severity": severity, "message": message}


def _get(record: dict, *keys: str, default=None) -> Any:
    """Safely walk nested keys."""
    node = record
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k, default)
    return node


# ---------------------------------------------------------------------------
# Individual rule functions
# ---------------------------------------------------------------------------

def check_required_fields(record: dict) -> list[dict]:
    issues = []
    for field in REQUIRED_TOP_LEVEL:
        if field not in record or record[field] is None:
            issues.append(_issue(
                "MISSING_REQUIRED_FIELD",
                "high",
                f"Required field '{field}' is missing or null."
            ))
    return issues


def check_record_id(record: dict) -> list[dict]:
    issues = []
    rid = record.get("record_id")
    if rid and not isinstance(rid, str):
        issues.append(_issue("INVALID_RECORD_ID", "high", "record_id must be a string."))
    elif rid and not rid.strip():
        issues.append(_issue("EMPTY_RECORD_ID", "high", "record_id must not be blank."))
    return issues


def check_location(record: dict) -> list[dict]:
    issues = []
    location = record.get("location", {})
    for field in ["state", "district", "tehsil", "village"]:
        val = location.get(field)
        if not val or not isinstance(val, str) or not val.strip():
            issues.append(_issue(
                "MISSING_LOCATION_FIELD",
                "medium",
                f"Location field '{field}' is missing or blank."
            ))
    return issues


def check_land_details(record: dict) -> list[dict]:
    issues = []
    ld = record.get("land_details", {})

    # khasra_number
    khasra = ld.get("khasra_number")
    if not khasra or not isinstance(khasra, str) or not khasra.strip():
        issues.append(_issue("MISSING_KHASRA", "high", "khasra_number is missing or blank."))

    # area – must be a positive number
    area = ld.get("area")
    if area is None:
        issues.append(_issue("MISSING_AREA", "high", "area is missing."))
    elif not isinstance(area, (int, float)):
        issues.append(_issue("INVALID_AREA_TYPE", "high",
                             "area must be a number (int or float), not a string."))
    elif area <= 0:
        issues.append(_issue("NON_POSITIVE_AREA", "high", "area must be greater than 0."))

    # area_unit
    area_unit = ld.get("area_unit", "")
    if area_unit not in ALLOWED_AREA_UNITS:
        issues.append(_issue("INVALID_AREA_UNIT", "medium",
                             f"area_unit '{area_unit}' is not recognised. "
                             f"Allowed: {sorted(ALLOWED_AREA_UNITS)}."))

    # area range check (only if type is valid)
    if isinstance(area, (int, float)) and area > 0 and area_unit in MAX_AREA:
        if area > MAX_AREA[area_unit]:
            issues.append(_issue("AREA_UNREASONABLY_LARGE", "medium",
                                 f"area {area} {area_unit} exceeds the maximum plausible value "
                                 f"({MAX_AREA[area_unit]} {area_unit})."))

    # land_type
    land_type = ld.get("land_type", "")
    if land_type not in ALLOWED_LAND_TYPES:
        issues.append(_issue("INVALID_LAND_TYPE", "medium",
                             f"land_type '{land_type}' is not recognised. "
                             f"Allowed: {sorted(ALLOWED_LAND_TYPES)}."))

    return issues


def check_ownership(record: dict) -> list[dict]:
    issues = []
    owners = record.get("ownership", [])

    if not isinstance(owners, list) or len(owners) == 0:
        issues.append(_issue("MISSING_OWNERSHIP", "high", "ownership list is empty or missing."))
        return issues

    total_share = 0.0
    for idx, owner in enumerate(owners):
        name = owner.get("owner_name", "")
        if not name or not isinstance(name, str) or not name.strip():
            issues.append(_issue("MISSING_OWNER_NAME", "high",
                                 f"owner_name is missing for ownership entry #{idx + 1}."))

        share = owner.get("share")
        if share is None:
            issues.append(_issue("MISSING_SHARE", "medium",
                                 f"share is missing for owner '{name or idx + 1}'."))
        elif not isinstance(share, (int, float)):
            issues.append(_issue("INVALID_SHARE_TYPE", "medium",
                                 f"share for owner '{name or idx + 1}' must be a number."))
        elif not (0.0 < share <= 1.0):
            issues.append(_issue("SHARE_OUT_OF_RANGE", "medium",
                                 f"share for owner '{name or idx + 1}' must be between 0 and 1."))
        else:
            total_share += share

    # Allow small floating-point tolerance
    if owners and abs(total_share - 1.0) > 0.01:
        issues.append(_issue("SHARE_SUM_MISMATCH", "high",
                             f"Total ownership share sums to {round(total_share, 4)}, expected 1.0."))

    return issues


def check_mutation(record: dict) -> list[dict]:
    issues = []
    mutation = record.get("mutation")
    if not mutation:
        return issues  # mutation is optional

    mut_type = mutation.get("mutation_type", "")
    if mut_type and mut_type not in ALLOWED_MUTATION_TYPES:
        issues.append(_issue("INVALID_MUTATION_TYPE", "low",
                             f"mutation_type '{mut_type}' is not recognised. "
                             f"Allowed: {sorted(ALLOWED_MUTATION_TYPES)}."))

    mut_date = mutation.get("mutation_date")
    if mut_date:
        try:
            from datetime import date
            parsed = date.fromisoformat(str(mut_date))
            if parsed > date.today():
                issues.append(_issue("FUTURE_MUTATION_DATE", "medium",
                                     f"mutation_date '{mut_date}' is in the future."))
        except ValueError:
            issues.append(_issue("INVALID_MUTATION_DATE", "medium",
                                 f"mutation_date '{mut_date}' is not a valid ISO date (YYYY-MM-DD)."))

    return issues


def check_extraction_confidence(record: dict) -> list[dict]:
    issues = []
    extraction = record.get("extraction")
    if not extraction:
        return issues  # extraction block may not be present yet

    overall = extraction.get("overall_confidence")
    if overall is not None:
        if not isinstance(overall, (int, float)):
            issues.append(_issue("INVALID_CONFIDENCE_TYPE", "low",
                                 "overall_confidence must be a number."))
        elif not (MIN_CONFIDENCE <= overall <= MAX_CONFIDENCE):
            issues.append(_issue("CONFIDENCE_OUT_OF_RANGE", "low",
                                 f"overall_confidence {overall} is outside [0, 1]."))
        elif overall < 0.6:
            issues.append(_issue("LOW_OCR_CONFIDENCE", "medium",
                                 f"overall_confidence {overall} is below threshold 0.6. "
                                 "Manual review recommended."))

    field_conf = extraction.get("field_confidence", {})
    for field, score in field_conf.items():
        if isinstance(score, (int, float)) and score < 0.5:
            issues.append(_issue("LOW_FIELD_CONFIDENCE", "low",
                                 f"Confidence for '{field}' is very low ({score}). "
                                 "Verify this field manually."))

    return issues


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_field_rules(record: dict) -> list[dict]:
    """
    Run all field-level rules on a LandRecord dict.
    Returns a flat list of issue dicts.
    """
    issues = []
    issues += check_required_fields(record)
    issues += check_record_id(record)
    issues += check_location(record)
    issues += check_land_details(record)
    issues += check_ownership(record)
    issues += check_mutation(record)
    issues += check_extraction_confidence(record)
    return issues
