"""Compare lab results between reports and describe trends.

Pure Python, no AI: every number shown to the user is calculated here,
so comparisons are exact and repeatable.
"""

import re

# Changes smaller than this (as a fraction of the old value) count as "stable".
STABLE_THRESHOLD = 0.05


def normalize_test_name(name: str) -> str:
    """Normalise a test name so the same test matches across reports.

    "CALCIUM, SERUM" and "Calcium Serum" -> "calcium serum"
    """
    name = re.sub(r"\([^)]*\)", " ", name or "")
    name = re.sub(r"[^a-z0-9]+", " ", name.lower())
    return " ".join(name.split())


def _direction(old: float, new: float) -> str:
    if old == 0:
        return "stable" if new == 0 else ("increased" if new > 0 else "decreased")
    change = (new - old) / abs(old)
    if abs(change) < STABLE_THRESHOLD:
        return "stable"
    return "increased" if change > 0 else "decreased"


def _status_change(old_status: str, new_status: str) -> str:
    old_bad, new_bad = old_status != "NORMAL", new_status != "NORMAL"
    if not old_bad and new_bad:
        return "newly outside range"
    if old_bad and not new_bad:
        return "now within range"
    if old_bad and new_bad:
        return "still outside range"
    return "within range"


def compare_reports(old_rows: list[dict], new_rows: list[dict]) -> list[dict]:
    """Compare two lists of lab results (each row: test, value, unit, status, reference_range).

    Returns one row per test found in either report.
    """
    old_by_key = {normalize_test_name(r["test"]): r for r in old_rows}
    new_by_key = {normalize_test_name(r["test"]): r for r in new_rows}
    result = []

    for key in sorted(set(old_by_key) | set(new_by_key)):
        old, new = old_by_key.get(key), new_by_key.get(key)
        row = {
            "test": (new or old)["test"],
            "old_value": old["value"] if old else None,
            "new_value": new["value"] if new else None,
            "unit": (new or old).get("unit", ""),
            "old_status": old["status"] if old else None,
            "new_status": new["status"] if new else None,
            "reference_range": (new or old).get("reference_range", ""),
            "change": None,
            "change_percent": None,
            "direction": None,
            "status_change": None,
        }
        if old and new:
            if (old.get("unit") or "").lower() != (new.get("unit") or "").lower():
                row["direction"] = "units differ - not compared"
            else:
                row["change"] = round(new["value"] - old["value"], 4)
                if old["value"]:
                    row["change_percent"] = round(row["change"] / abs(old["value"]) * 100, 1)
                row["direction"] = _direction(old["value"], new["value"])
            row["status_change"] = _status_change(old["status"], new["status"])
        elif new:
            row["direction"] = "new test"
        else:
            row["direction"] = "not in newer report"
        result.append(row)

    # Most important first: newly abnormal, still abnormal, improved, then the rest.
    order = {"newly outside range": 0, "still outside range": 1, "now within range": 2}
    result.sort(key=lambda r: (order.get(r["status_change"], 3), r["test"]))
    return result


def trend_direction(values: list[float]) -> str:
    """Overall direction of a series of values, oldest first."""
    if len(values) < 2:
        return "only one result"
    return _direction(values[0], values[-1])