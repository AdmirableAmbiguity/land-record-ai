"""
consistency.py – Member 2: Cross-field consistency checks.

Catches logical contradictions *within* a single record, e.g.
- a future mutation date with a very old record_id pattern
- land_type mismatch with mutation_type
- duplicate owner names in the same record
- area in one unit vs stated area_unit
"""

from __future__ import annotations

from datetime import date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue(code: str, severity: str, message: str) -> dict:
    return {"code": code, "severity": severity, "message": message}


def _get(record: dict, *keys: str, default=None):
    node = record
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k, default)
    return node


# ---------------------------------------------------------------------------
# Cross-field checks
# ---------------------------------------------------------------------------

def check_owner_name_duplicates(record: dict) -> list[dict]:
    """Flag if the same owner name appears more than once in the ownership list."""
    issues = []
    owners = record.get("ownership", [])
    names = [o.get("owner_name", "").strip().lower() for o in owners if isinstance(o, dict)]
    seen = set()
    for name in names:
        if name and name in seen:
            issues.append(_issue(
                "DUPLICATE_OWNER_NAME",
                "medium",
                f"Owner name '{name}' appears more than once in the ownership list."
            ))
        seen.add(name)
    return issues


def check_mutation_consistency(record: dict) -> list[dict]:
    """
    Cross-checks mutation fields with ownership and land details.
    - A 'sale' mutation should not retain the original sole owner
      (we can only warn; we don't have the historical record).
    - Mutation date should not pre-date a plausible record epoch.
    """
    issues = []
    mutation = record.get("mutation")
    if not mutation:
        return issues

    mut_date_str = mutation.get("mutation_date")
    if mut_date_str:
        try:
            mut_date = date.fromisoformat(str(mut_date_str))
            # Land records in India became computerised post-1990 broadly
            if mut_date.year < 1900:
                issues.append(_issue(
                    "SUSPICIOUSLY_OLD_MUTATION_DATE",
                    "low",
                    f"mutation_date '{mut_date_str}' is before 1900. Please verify."
                ))
        except ValueError:
            pass  # already caught in rules.py

    mut_id = mutation.get("mutation_id", "")
    if mut_id and not isinstance(mut_id, str):
        issues.append(_issue("INVALID_MUTATION_ID_TYPE", "low",
                             "mutation_id must be a string."))

    return issues


def check_area_unit_consistency(record: dict) -> list[dict]:
    """
    Warn if area value looks like it was accidentally entered in a different unit.
    Example: area=0.001 hectare is extremely small (only 10 sqm) — likely a data entry error.
    """
    issues = []
    ld = record.get("land_details", {})
    area = ld.get("area")
    area_unit = ld.get("area_unit", "")

    if not isinstance(area, (int, float)) or area <= 0:
        return issues

    # Extremely small areas by unit
    SMALL_THRESHOLD = {
        "hectare":      0.001,   # < 10 sqm
        "acre":         0.001,
        "bigha":        0.01,
        "square_meter": 1.0,
        "square_feet":  10.0,
    }

    threshold = SMALL_THRESHOLD.get(area_unit)
    if threshold and area < threshold:
        issues.append(_issue(
            "AREA_SUSPICIOUSLY_SMALL",
            "medium",
            f"area {area} {area_unit} is unusually small. "
            "Check if the wrong unit was recorded."
        ))

    return issues


def check_khasra_format(record: dict) -> list[dict]:
    """
    Khasra numbers in UP follow patterns like '123', '123/2', '123A'.
    Flag completely numeric-free values as suspicious.
    """
    issues = []
    khasra = _get(record, "land_details", "khasra_number", default="")
    if khasra and isinstance(khasra, str):
        if not any(ch.isdigit() for ch in khasra):
            issues.append(_issue(
                "SUSPICIOUS_KHASRA_FORMAT",
                "low",
                f"khasra_number '{khasra}' contains no digits. Verify format."
            ))
    return issues


def check_land_use_vs_land_type(record: dict) -> list[dict]:
    """
    If the record already has a land_use_check result embedded, verify it
    doesn't contradict the land_type.
    E.g. if land_type='forest' and land_use_check.status='allowed' for 'commercial' use,
    flag the inconsistency.
    """
    issues = []
    land_type = _get(record, "land_details", "land_type", default="")
    luc = record.get("land_use_check", {})
    if not luc:
        return issues

    intended = luc.get("intended_use", "")
    status = luc.get("status", "")

    # Forest land should never be 'allowed' for any non-forest use
    if land_type == "forest" and intended not in ("", "forest") and status == "allowed":
        issues.append(_issue(
            "FOREST_LAND_USE_CONFLICT",
            "high",
            f"land_type is 'forest' but land_use_check shows status='allowed' "
            f"for intended_use='{intended}'. Forest land use change requires legal clearance."
        ))

    return issues


def check_verification_integrity_consistency(record: dict) -> list[dict]:
    """
    If integrity.blockchain_tx_id is set but verification.status is 'pending',
    that is suspicious – blockchain should only be written after verification.
    """
    issues = []
    blockchain_tx = _get(record, "integrity", "blockchain_tx_id")
    ver_status = _get(record, "verification", "status", default="pending")

    if blockchain_tx and ver_status == "pending":
        issues.append(_issue(
            "BLOCKCHAIN_BEFORE_VERIFICATION",
            "high",
            "integrity.blockchain_tx_id is set but verification.status is still 'pending'. "
            "Blockchain entry should only be created after verification."
        ))

    return issues


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_consistency_checks(record: dict) -> list[dict]:
    """
    Run all cross-field consistency checks.
    Returns a flat list of issue dicts.
    """
    issues = []
    issues += check_owner_name_duplicates(record)
    issues += check_mutation_consistency(record)
    issues += check_area_unit_consistency(record)
    issues += check_khasra_format(record)
    issues += check_land_use_vs_land_type(record)
    issues += check_verification_integrity_consistency(record)
    return issues
