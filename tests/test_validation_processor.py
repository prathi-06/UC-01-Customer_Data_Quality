import json
from pathlib import Path
import pytest
from app.validation import validate_records
from app.processor import process_records

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

def load_json(filename: str):
    with open(FIXTURES_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)

# 1. Gate fixture tests
def test_valid_fixture():
    fixture = load_json("valid.json")
    result = validate_records(fixture["records"])
    assert result["valid_rows"] == 2
    assert result["invalid_rows"] == 0
    assert result["issues"] == []

def test_invalid_fixture():
    fixture = load_json("invalid.json")
    result = validate_records(fixture["records"])
    assert result["valid_rows"] == 2
    assert result["invalid_rows"] == 4
    expected_issues = [
        {"row_index": 3, "field": "record_id", "rule_id": "R1"},
        {"row_index": 4, "field": "email", "rule_id": "R2"},
        {"row_index": 5, "field": "credit_limit", "rule_id": "R3"},
        {"row_index": 6, "field": "status", "rule_id": "R4"},
    ]
    assert result["issues"] == expected_issues

def test_process_expected_fixture():
    valid_fixture = load_json("valid.json")
    expected_output = load_json("expected_process_output.json")
    result = process_records(valid_fixture["records"])
    assert result == expected_output

# Table-driven unit test cases (at least 20 cases)
TEST_CASES = [
    # Case 4: credit_limit boolean True is rejected
    (
        [{"record_id": "T01", "email": "user@example.com", "credit_limit": True, "status": "ACTIVE"}],
        0, 1, [("credit_limit", "R3")]
    ),
    # Case 5: credit_limit boolean False is rejected
    (
        [{"record_id": "T02", "email": "user@example.com", "credit_limit": False, "status": "ACTIVE"}],
        0, 1, [("credit_limit", "R3")]
    ),
    # Case 6: credit_limit numeric string is rejected
    (
        [{"record_id": "T03", "email": "user@example.com", "credit_limit": "500", "status": "ACTIVE"}],
        0, 1, [("credit_limit", "R3")]
    ),
    # Case 7: credit_limit float 500.0 is rejected
    (
        [{"record_id": "T04", "email": "user@example.com", "credit_limit": 500.0, "status": "ACTIVE"}],
        0, 1, [("credit_limit", "R3")]
    ),
    # Case 8: credit_limit lower bound (0) is valid
    (
        [{"record_id": "T05", "email": "user@example.com", "credit_limit": 0, "status": "ACTIVE"}],
        1, 0, []
    ),
    # Case 9: credit_limit upper bound (100000) is valid
    (
        [{"record_id": "T06", "email": "user@example.com", "credit_limit": 100000, "status": "ACTIVE"}],
        1, 0, []
    ),
    # Case 10: credit_limit out of bound (100001) is rejected
    (
        [{"record_id": "T07", "email": "user@example.com", "credit_limit": 100001, "status": "ACTIVE"}],
        0, 1, [("credit_limit", "R3")]
    ),
    # Case 11: whitespace trimming on email and status keeps row valid
    (
        [{"record_id": "  T08  ", "email": "  user@domain.org  ", "credit_limit": 250, "status": "  ACTIVE  "}],
        1, 0, []
    ),
    # Case 12: case-sensitive IDs are distinct and both valid
    (
        [
            {"record_id": "abc", "email": "u1@domain.com", "credit_limit": 10, "status": "ACTIVE"},
            {"record_id": "ABC", "email": "u2@domain.com", "credit_limit": 20, "status": "ACTIVE"},
        ],
        2, 0, []
    ),
    # Case 13: first occurrence of duplicate ID stays valid, second fails
    (
        [
            {"record_id": "DUP1", "email": "u1@domain.com", "credit_limit": 10, "status": "ACTIVE"},
            {"record_id": "DUP1", "email": "u2@domain.com", "credit_limit": 20, "status": "ACTIVE"},
        ],
        1, 1, [("record_id", "R1")]
    ),
    # Case 14: row failing several rules counts once as invalid row
    (
        [
            {"record_id": "", "email": "not-an-email", "credit_limit": -5, "status": "PENDING"}
        ],
        0, 1, [("record_id", "R1"), ("email", "R2"), ("credit_limit", "R3"), ("status", "R4")]
    ),
    # Case 15: non-string record_id (integer) rejected by R1
    (
        [{"record_id": 12345, "email": "u@domain.com", "credit_limit": 100, "status": "ACTIVE"}],
        0, 1, [("record_id", "R1")]
    ),
    # Case 16: non-string email (None) rejected by R2
    (
        [{"record_id": "T16", "email": None, "credit_limit": 100, "status": "ACTIVE"}],
        0, 1, [("email", "R2")]
    ),
    # Case 17: non-string status (dict) rejected by R4
    (
        [{"record_id": "T17", "email": "u@domain.com", "credit_limit": 100, "status": {"foo": "bar"}}],
        0, 1, [("status", "R4")]
    ),
    # Case 18: 20-character record_id is valid
    (
        [{"record_id": "12345678901234567890", "email": "u@domain.com", "credit_limit": 100, "status": "ACTIVE"}],
        1, 0, []
    ),
    # Case 19: 21-character record_id is rejected by R1
    (
        [{"record_id": "123456789012345678901", "email": "u@domain.com", "credit_limit": 100, "status": "ACTIVE"}],
        0, 1, [("record_id", "R1")]
    ),
    # Case 20: email missing @ rejected by R2
    (
        [{"record_id": "T20", "email": "username.domain.com", "credit_limit": 100, "status": "ACTIVE"}],
        0, 1, [("email", "R2")]
    ),
    # Case 21: email missing dot rejected by R2
    (
        [{"record_id": "T21", "email": "username@domain", "credit_limit": 100, "status": "ACTIVE"}],
        0, 1, [("email", "R2")]
    ),
    # Case 22: email with internal spaces rejected by R2
    (
        [{"record_id": "T22", "email": "user name@domain.com", "credit_limit": 100, "status": "ACTIVE"}],
        0, 1, [("email", "R2")]
    ),
    # Case 23: email with double @@ rejected by R2
    (
        [{"record_id": "T23", "email": "user@@domain.com", "credit_limit": 100, "status": "ACTIVE"}],
        0, 1, [("email", "R2")]
    ),
    # Case 24: status INACTIVE is valid
    (
        [{"record_id": "T24", "email": "user@example.com", "credit_limit": 50, "status": "INACTIVE"}],
        1, 0, []
    ),
    # Case 25: status lowercase 'active' rejected by R4
    (
        [{"record_id": "T25", "email": "user@example.com", "credit_limit": 50, "status": "active"}],
        0, 1, [("status", "R4")]
    )
]

@pytest.mark.parametrize("records, expected_valid, expected_invalid, expected_field_rules", TEST_CASES)
def test_table_driven_cases(records, expected_valid, expected_invalid, expected_field_rules):
    result = validate_records(records)
    assert result["valid_rows"] == expected_valid
    assert result["invalid_rows"] == expected_invalid
    
    actual_field_rules = [(iss["field"], iss["rule_id"]) for iss in result["issues"]]
    assert actual_field_rules == expected_field_rules

def test_processor_logic():
    records = [
        {"record_id": " R1 ", "email": " ALICE@Corp.Com ", "credit_limit": 100, "status": "ACTIVE"},
        {"record_id": " R2 ", "email": " BOB@Corp.Com ", "credit_limit": 200, "status": "INACTIVE"},
    ]
    res = process_records(records)
    assert res["summary"]["input_rows"] == 2
    assert res["summary"]["contactable_rows"] == 1
    assert res["rows"][0] == {"record_id": "R1", "email": "alice@corp.com", "contactable": True}
    assert res["rows"][1] == {"record_id": "R2", "email": "bob@corp.com", "contactable": False}
    assert res["issues"] == []
