import re
from typing import Any, Dict, List, Tuple

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ALLOWED_FIELDS = {"record_id", "email", "credit_limit", "status"}

def validate_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    r"""
    Validate a batch of customer records according to rules R1 to R4:
    R1: record_id is a nonempty string of at most 20 characters and is unique within the batch.
    R2: email matches ^[^@\s]+@[^@\s]+\.[^@\s]+$ after trimming spaces.
    R3: credit_limit is an integer from 0 to 100000 inclusive.
    R4: status is ACTIVE or INACTIVE.

    Returns:
        {
            "valid_rows": int,
            "invalid_rows": int,
            "issues": [
                {"row_index": int, "field": str, "rule_id": str}
            ]
        }
    """
    issues: List[Dict[str, Any]] = []
    seen_ids = set()
    invalid_rows_indices = set()

    for idx, rec in enumerate(records, start=1):
        row_has_issue = False

        # R1: record_id
        rec_id = rec.get("record_id")
        if not isinstance(rec_id, str):
            issues.append({"row_index": idx, "field": "record_id", "rule_id": "R1"})
            row_has_issue = True
        else:
            trimmed_id = rec_id.strip()
            if len(trimmed_id) == 0 or len(trimmed_id) > 20:
                issues.append({"row_index": idx, "field": "record_id", "rule_id": "R1"})
                row_has_issue = True
            elif trimmed_id in seen_ids:
                issues.append({"row_index": idx, "field": "record_id", "rule_id": "R1"})
                row_has_issue = True
            else:
                seen_ids.add(trimmed_id)

        # R2: email
        email_val = rec.get("email")
        if not isinstance(email_val, str):
            issues.append({"row_index": idx, "field": "email", "rule_id": "R2"})
            row_has_issue = True
        else:
            trimmed_email = email_val.strip()
            if not EMAIL_REGEX.match(trimmed_email):
                issues.append({"row_index": idx, "field": "email", "rule_id": "R2"})
                row_has_issue = True

        # R3: credit_limit (strictly integer, no bool, no numeric strings, 0..100000)
        credit_val = rec.get("credit_limit")
        if isinstance(credit_val, bool) or type(credit_val) is not int:
            issues.append({"row_index": idx, "field": "credit_limit", "rule_id": "R3"})
            row_has_issue = True
        elif not (0 <= credit_val <= 100000):
            issues.append({"row_index": idx, "field": "credit_limit", "rule_id": "R3"})
            row_has_issue = True

        # R4: status (ACTIVE or INACTIVE)
        status_val = rec.get("status")
        if not isinstance(status_val, str):
            issues.append({"row_index": idx, "field": "status", "rule_id": "R4"})
            row_has_issue = True
        else:
            trimmed_status = status_val.strip()
            if trimmed_status not in ("ACTIVE", "INACTIVE"):
                issues.append({"row_index": idx, "field": "status", "rule_id": "R4"})
                row_has_issue = True

        if row_has_issue:
            invalid_rows_indices.add(idx)

    total_rows = len(records)
    invalid_count = len(invalid_rows_indices)
    valid_count = total_rows - invalid_count

    return {
        "valid_rows": valid_count,
        "invalid_rows": invalid_count,
        "issues": issues,
    }
