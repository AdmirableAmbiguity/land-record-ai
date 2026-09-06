"""
validator.py – Member 2: Main entry point for the validation module.

Usage (called by Member 4's API layer):

    from backend.validation.validator import validate_record

    result = validate_record(land_record_json, related_records=[...])
"""

from __future__ import annotations

from .rules import run_field_rules
from .consistency import run_consistency_checks
from .anomaly import run_anomaly_checks


def validate_record(
    record: dict,
    related_records: list[dict] | None = None
) -> dict:
    """
    Full validation pipeline for a LandRecord JSON.

    Args:
        record:          The LandRecord dict to validate.
        related_records: Other records from the DB for the same parcel/area (optional).

    Returns a Validation Result dict:
    {
        "record_id":      "LR-0001",
        "status":         "valid" | "needs_review" | "invalid",
        "anomaly_score":  0.12,
        "issues": [
            {
                "code":     "AREA_MISMATCH",
                "severity": "high",
                "message":  "..."
            },
            ...
        ]
    }
    """
    all_issues: list[dict] = []

    # Step 1 – field-level rules
    all_issues += run_field_rules(record)

    # Step 2 – cross-field consistency
    all_issues += run_consistency_checks(record)

    # Step 3 – multi-record anomaly detection
    anomaly_issues, anomaly_score = run_anomaly_checks(record, related_records)
    all_issues += anomaly_issues

    # Deduplicate by (code, message)
    seen = set()
    unique_issues = []
    for iss in all_issues:
        key = (iss["code"], iss["message"])
        if key not in seen:
            seen.add(key)
            unique_issues.append(iss)

    # Determine overall status
    has_high = any(i["severity"] == "high" for i in unique_issues)
    has_medium = any(i["severity"] == "medium" for i in unique_issues)

    if has_high:
        status = "invalid"
    elif has_medium:
        status = "needs_review"
    elif unique_issues:
        status = "needs_review"
    else:
        status = "valid"

    return {
        "record_id":     record.get("record_id", "UNKNOWN"),
        "status":        status,
        "anomaly_score": anomaly_score,
        "issues":        unique_issues,
    }
