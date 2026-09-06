"""
tests/run_tests.py – Standalone test runner (no pytest needed).

Run: python3 tests/run_tests.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.validation.rules import run_field_rules
from backend.validation.consistency import run_consistency_checks
from backend.validation.anomaly import run_anomaly_checks, compute_anomaly_score
from backend.validation.validator import validate_record

GOOD_RECORD = {
    "record_id": "LR-0001",
    "source_document": {"file_name": "record.pdf", "file_type": "pdf", "page_count": 3},
    "location": {"state": "Uttar Pradesh", "district": "Ghaziabad", "tehsil": "Loni", "village": "Example Village"},
    "land_details": {"khasra_number": "123/2", "khata_number": "45", "area": 2.4, "area_unit": "hectare", "land_type": "agricultural"},
    "ownership": [{"owner_name": "Ram Singh", "share": 1.0}],
    "mutation": {"mutation_id": "M-123", "mutation_date": "2020-05-12", "mutation_type": "sale"},
    "extraction": {"method": "ocr_vlm", "overall_confidence": 0.91, "field_confidence": {"owner_name": 0.96, "khasra_number": 0.94, "area": 0.88, "land_type": 0.91}},
    "validation": {"status": "needs_review", "issues": []},
    "land_use_check": {"intended_use": "residential", "status": "restricted", "reason": "Permission may be required."},
    "verification": {"status": "pending", "verified_by": None, "verified_at": None},
    "integrity": {"record_hash": None, "blockchain_tx_id": None}
}

passed = failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  ✅ PASS  {name}")
        passed += 1
    else:
        print(f"  ❌ FAIL  {name}" + (f" | {detail}" if detail else ""))
        failed += 1

def codes(issues): return [i["code"] for i in issues]

print("\n── rules.py ─────────────────────────────────")
check("good record → no field issues", run_field_rules(GOOD_RECORD) == [])
check("missing record_id → MISSING_REQUIRED_FIELD", "MISSING_REQUIRED_FIELD" in codes(run_field_rules({**{k:v for k,v in GOOD_RECORD.items() if k!="record_id"}})))
check("area as string → INVALID_AREA_TYPE", "INVALID_AREA_TYPE" in codes(run_field_rules({**GOOD_RECORD, "land_details": {**GOOD_RECORD["land_details"], "area": "2.4 hectares"}})))
check("negative area → NON_POSITIVE_AREA", "NON_POSITIVE_AREA" in codes(run_field_rules({**GOOD_RECORD, "land_details": {**GOOD_RECORD["land_details"], "area": -1.0}})))
check("invalid land_type → INVALID_LAND_TYPE", "INVALID_LAND_TYPE" in codes(run_field_rules({**GOOD_RECORD, "land_details": {**GOOD_RECORD["land_details"], "land_type": "lunar"}})))
check("share sum ≠ 1 → SHARE_SUM_MISMATCH", "SHARE_SUM_MISMATCH" in codes(run_field_rules({**GOOD_RECORD, "ownership": [{"owner_name": "A", "share": 0.6}, {"owner_name": "B", "share": 0.1}]})))
check("future mutation → FUTURE_MUTATION_DATE", "FUTURE_MUTATION_DATE" in codes(run_field_rules({**GOOD_RECORD, "mutation": {**GOOD_RECORD["mutation"], "mutation_date": "2099-01-01"}})))
check("low confidence → LOW_OCR_CONFIDENCE", "LOW_OCR_CONFIDENCE" in codes(run_field_rules({**GOOD_RECORD, "extraction": {**GOOD_RECORD["extraction"], "overall_confidence": 0.45}})))
check("missing district → MISSING_LOCATION_FIELD", "MISSING_LOCATION_FIELD" in codes(run_field_rules({**GOOD_RECORD, "location": {k:v for k,v in GOOD_RECORD["location"].items() if k!="district"}})))

print("\n── consistency.py ────────────────────────────")
check("good record → no consistency issues", run_consistency_checks(GOOD_RECORD) == [])
check("duplicate owner → DUPLICATE_OWNER_NAME", "DUPLICATE_OWNER_NAME" in codes(run_consistency_checks({**GOOD_RECORD, "ownership": [{"owner_name": "Ram Singh", "share": 0.5}, {"owner_name": "Ram Singh", "share": 0.5}]})))
check("tiny area → AREA_SUSPICIOUSLY_SMALL", "AREA_SUSPICIOUSLY_SMALL" in codes(run_consistency_checks({**GOOD_RECORD, "land_details": {**GOOD_RECORD["land_details"], "area": 0.0001}})))
check("blockchain before verify → BLOCKCHAIN_BEFORE_VERIFICATION", "BLOCKCHAIN_BEFORE_VERIFICATION" in codes(run_consistency_checks({**GOOD_RECORD, "integrity": {"record_hash": "abc", "blockchain_tx_id": "TX-99"}})))
check("forest land allowed → FOREST_LAND_USE_CONFLICT", "FOREST_LAND_USE_CONFLICT" in codes(run_consistency_checks({**GOOD_RECORD, "land_details": {**GOOD_RECORD["land_details"], "land_type": "forest"}, "land_use_check": {"intended_use": "commercial", "status": "allowed", "reason": ""}})))

print("\n── anomaly.py ────────────────────────────────")
issues0, score0 = run_anomaly_checks(GOOD_RECORD)
check("single good record → no anomalies", issues0 == [] and score0 == 0.0)
rec2 = {**GOOD_RECORD, "record_id": "LR-0002"}
i_dup, _ = run_anomaly_checks(GOOD_RECORD, [rec2])
check("same parcel two records → DUPLICATE_RECORDS", "DUPLICATE_RECORDS" in codes(i_dup))
rec_area = {**GOOD_RECORD, "record_id": "LR-0002", "land_details": {**GOOD_RECORD["land_details"], "area": 5.0}}
i_area, _ = run_anomaly_checks(GOOD_RECORD, [rec_area])
check("area differs 108% → AREA_MISMATCH", "AREA_MISMATCH" in codes(i_area))
rec_owner = {**GOOD_RECORD, "record_id": "LR-0002", "ownership": [{"owner_name": "Geeta Devi", "share": 1.0}]}
i_own, _ = run_anomaly_checks(GOOD_RECORD, [rec_owner])
check("different owners → OWNERSHIP_CONFLICT", "OWNERSHIP_CONFLICT" in codes(i_own))
big_issues = [{"code": f"X{i}", "severity": "high", "message": ""} for i in range(20)]
check("anomaly score capped at 1.0", compute_anomaly_score(big_issues) <= 1.0)

print("\n── validator.py (integration) ─────────────")
r_good = validate_record(GOOD_RECORD)
check("valid record → status=valid", r_good["status"] == "valid", r_good)
check("valid record → anomaly_score=0.0", r_good["anomaly_score"] == 0.0)
check("valid record → no issues", r_good["issues"] == [])
bad = {k:v for k,v in GOOD_RECORD.items() if k not in ("record_id", "location")}
r_bad = validate_record(bad)
check("bad record → status=invalid", r_bad["status"] == "invalid")
check("result has all required keys", all(k in r_good for k in ("record_id","status","anomaly_score","issues")))
r_str_area = validate_record({**GOOD_RECORD, "land_details": {**GOOD_RECORD["land_details"], "area": "2.4 hectares"}})
iss_fmt = r_str_area["issues"]
check("each issue has code/severity/message", all("code" in i and "severity" in i and "message" in i for i in iss_fmt))

print(f"\n{'='*46}")
print(f"  Results: {passed} passed, {failed} failed out of {passed+failed} tests")
print(f"{'='*46}\n")
sys.exit(0 if failed == 0 else 1)
