from typing import Any, Dict, List

def process_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Supplied processor for UC-01 Customer Data Quality:
    Lowercases trimmed email addresses and sets contactable to true only when status is ACTIVE.
    Preserves row order.

    Returns:
        {
            "summary": {
                "input_rows": int,
                "contactable_rows": int
            },
            "rows": [
                {
                    "record_id": str,
                    "email": str,
                    "contactable": bool
                }
            ],
            "issues": []
        }
    """
    processed_rows = []
    contactable_count = 0

    for rec in records:
        rec_id = rec["record_id"].strip()
        email = rec["email"].strip().lower()
        contactable = (rec["status"].strip() == "ACTIVE")
        if contactable:
            contactable_count += 1

        processed_rows.append({
            "record_id": rec_id,
            "email": email,
            "contactable": contactable
        })

    return {
        "summary": {
            "input_rows": len(records),
            "contactable_rows": contactable_count
        },
        "rows": processed_rows,
        "issues": []
    }
