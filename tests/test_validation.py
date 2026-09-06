"""
tests/test_validation.py – Member 6 friendly test suite.

Run with:
    python -m pytest tests/test_validation.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from backend.validation.rules import run_field_rules
from backend.validation.consistency import run_consistency_checks
from backend.validation.anomaly import run_anomaly_checks, compute_anomaly_score
from backend.validation.validator import validate_record


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GOOD_RECORD = {
    "record_id": "LR-0001",
    "source_document": {"file_name": "record.pdf", "file_type": "pdf", "page_count": 3},
    "location": {
        "state": "Uttar Pradesh",
        "district": "Ghaziabad",
        "tehsil": "Loni",
        "village": "Example Village"
    },
    "land_details": {
        "khasra_number": "123/2",
        "khata_number": "45",
        "area": 2.4,
        "area_unit": "hectare",
        "land_type": "agricultural"
    },
    "ownership": [{"owner_name": "Ram Singh", "share": 1.0}],
    "mutation": {
        "mutation_id": "M-123",
        "mutation_date": "2020-05-12",
        "mutation_type": "sale"
    },
    "extraction": {
        "method": "ocr_vlm",
        "overall_confidence": 0.91,
        "field_confidence": {
            "owner_name": 0.96,
            "khasra_number": 0.94,
            "area": 0.88,
            "land_type": 0.91
        }
    },
    "validation": {"status": "needs_review", "issues": []},
    "land_use_check": {"intended_use": "residential", "status": "restricted",
                       "reason": "Permission may be required."},
    "verification": {"status": "pending", "verified_by": None, "verified_at": None},
    "integrity": {"record_hash": None, "blockchain_tx_id": None}
}


# ---------------------------------------------------------------------------
# rules.py tests
# ---------------------------------------------------------------------------

class TestFieldRules:
    def test_good_record_no_issues(self):
        issues = run_field_rules(GOOD_RECORD)
        assert issues == [], f"Expected no issues, got: {issues}"

    def test_missing_record_id(self):
        rec = {**GOOD_RECORD}
        del rec["record_id"]
        issues = run_field_rules(rec)
        codes = [i["code"] for i in issues]
        assert "MISSING_REQUIRED_FIELD" in codes

    def test_area_as_string_flagged(self):
        """area must be a number, not '2.4 hectares'."""
        rec = {**GOOD_RECORD,
               "land_details": {**GOOD_RECORD["land_details"], "area": "2.4 hectares"}}
        issues = run_field_rules(rec)
        codes = [i["code"] for i in issues]
        assert "INVALID_AREA_TYPE" in codes

    def test_negative_area(self):
        rec = {**GOOD_RECORD,
               "land_details": {**GOOD_RECORD["land_details"], "area": -1.0}}
        issues = run_field_rules(rec)
        codes = [i["code"] for i in issues]
        assert "NON_POSITIVE_AREA" in codes

    def test_invalid_land_type(self):
        rec = {**GOOD_RECORD,
               "land_details": {**GOOD_RECORD["land_details"], "land_type": "lunar"}}
        issues = run_field_rules(rec)
        codes = [i["code"] for i in issues]
        assert "INVALID_LAND_TYPE" in codes

    def test_share_sum_not_one(self):
        rec = {**GOOD_RECORD,
               "ownership": [
                   {"owner_name": "Ram Singh", "share": 0.6},
                   {"owner_name": "Shyam Kumar", "share": 0.1}
               ]}
        issues = run_field_rules(rec)
        codes = [i["code"] for i in issues]
        assert "SHARE_SUM_MISMATCH" in codes

    def test_future_mutation_date(self):
        rec = {**GOOD_RECORD,
               "mutation": {**GOOD_RECORD["mutation"], "mutation_date": "2099-01-01"}}
        issues = run_field_rules(rec)
        codes = [i["code"] for i in issues]
        assert "FUTURE_MUTATION_DATE" in codes

    def test_low_confidence_warning(self):
        rec = {**GOOD_RECORD,
               "extraction": {**GOOD_RECORD["extraction"], "overall_confidence": 0.45}}
        issues = run_field_rules(rec)
        codes = [i["code"] for i in issues]
        assert "LOW_OCR_CONFIDENCE" in codes

    def test_missing_location_field(self):
        loc = {**GOOD_RECORD["location"]}
        del loc["district"]
        rec = {**GOOD_RECORD, "location": loc}
        issues = run_field_rules(rec)
        codes = [i["code"] for i in issues]
        assert "MISSING_LOCATION_FIELD" in codes


# ---------------------------------------------------------------------------
# consistency.py tests
# ---------------------------------------------------------------------------

class TestConsistency:
    def test_good_record_no_issues(self):
        issues = run_consistency_checks(GOOD_RECORD)
        assert issues == []

    def test_duplicate_owner_name(self):
        rec = {**GOOD_RECORD,
               "ownership": [
                   {"owner_name": "Ram Singh", "share": 0.5},
                   {"owner_name": "Ram Singh", "share": 0.5},
               ]}
        issues = run_consistency_checks(rec)
        codes = [i["code"] for i in issues]
        assert "DUPLICATE_OWNER_NAME" in codes

    def test_suspiciously_small_area(self):
        rec = {**GOOD_RECORD,
               "land_details": {**GOOD_RECORD["land_details"], "area": 0.0001}}
        issues = run_consistency_checks(rec)
        codes = [i["code"] for i in issues]
        assert "AREA_SUSPICIOUSLY_SMALL" in codes

    def test_blockchain_before_verification(self):
        rec = {**GOOD_RECORD,
               "integrity": {"record_hash": "abc123", "blockchain_tx_id": "TX-99"},
               "verification": {"status": "pending", "verified_by": None, "verified_at": None}}
        issues = run_consistency_checks(rec)
        codes = [i["code"] for i in issues]
        assert "BLOCKCHAIN_BEFORE_VERIFICATION" in codes

    def test_forest_land_allowed_conflict(self):
        rec = {**GOOD_RECORD,
               "land_details": {**GOOD_RECORD["land_details"], "land_type": "forest"},
               "land_use_check": {"intended_use": "commercial", "status": "allowed",
                                  "reason": ""}}
        issues = run_consistency_checks(rec)
        codes = [i["code"] for i in issues]
        assert "FOREST_LAND_USE_CONFLICT" in codes


# ---------------------------------------------------------------------------
# anomaly.py tests
# ---------------------------------------------------------------------------

class TestAnomalyDetection:
    def test_no_anomalies_single_record(self):
        issues, score = run_anomaly_checks(GOOD_RECORD)
        assert issues == []
        assert score == 0.0

    def test_duplicate_records(self):
        rec2 = {**GOOD_RECORD, "record_id": "LR-0002"}
        issues, score = run_anomaly_checks(GOOD_RECORD, [rec2])
        codes = [i["code"] for i in issues]
        assert "DUPLICATE_RECORDS" in codes
        assert score > 0

    def test_area_mismatch(self):
        rec2 = {
            **GOOD_RECORD,
            "record_id": "LR-0002",
            "land_details": {**GOOD_RECORD["land_details"], "area": 5.0}  # very different
        }
        issues, score = run_anomaly_checks(GOOD_RECORD, [rec2])
        codes = [i["code"] for i in issues]
        assert "AREA_MISMATCH" in codes

    def test_ownership_conflict(self):
        rec2 = {
            **GOOD_RECORD,
            "record_id": "LR-0002",
            "ownership": [{"owner_name": "Geeta Devi", "share": 1.0}]
        }
        issues, score = run_anomaly_checks(GOOD_RECORD, [rec2])
        codes = [i["code"] for i in issues]
        assert "OWNERSHIP_CONFLICT" in codes

    def test_anomaly_score_capped_at_one(self):
        many_high_issues = [{"code": f"X{i}", "severity": "high", "message": ""} for i in range(20)]
        score = compute_anomaly_score(many_high_issues)
        assert score <= 1.0


# ---------------------------------------------------------------------------
# validator.py (integration) tests
# ---------------------------------------------------------------------------

class TestValidator:
    def test_valid_record_returns_valid(self):
        result = validate_record(GOOD_RECORD)
        assert result["status"] == "valid"
        assert result["record_id"] == "LR-0001"
        assert result["issues"] == []
        assert result["anomaly_score"] == 0.0

    def test_invalid_record_returns_invalid(self):
        bad = {**GOOD_RECORD}
        del bad["record_id"]
        del bad["location"]
        result = validate_record(bad)
        assert result["status"] == "invalid"
        assert len(result["issues"]) > 0

    def test_result_contains_required_keys(self):
        result = validate_record(GOOD_RECORD)
        for key in ("record_id", "status", "anomaly_score", "issues"):
            assert key in result

    def test_issue_format(self):
        bad = {**GOOD_RECORD,
               "land_details": {**GOOD_RECORD["land_details"], "area": "2.4 hectares"}}
        result = validate_record(bad)
        for iss in result["issues"]:
            assert "code" in iss
            assert "severity" in iss
            assert "message" in iss


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
