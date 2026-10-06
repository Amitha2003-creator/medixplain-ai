"""
MediXplain AI - Laboratory value extraction.

Educational use only. This module reads numbers from a report and compares
each result with the reference range printed in that same report.
It does NOT diagnose anything.

Main function:
    analyze_lab_values(text) -> list of dicts

Each dict looks like:
    {
        "test": "CALCIUM, SERUM",
        "value": 9.1,
        "value_text": "9.10",
        "unit": "mg/dL",
        "reference_range": "8.4 - 10.2",
        "low": 8.4,
        "high": 10.2,
        "status": "NORMAL",      # NORMAL / HIGH / LOW
    }

Supported row layouts (same line or table-like PDF text):
    Test | Unit | Range | Result     e.g.  CALCIUM, SERUM mg/dL 8.4 - 10.2 9.10
    Test | Range | Unit | Result     e.g.  CALCIUM 8.4 - 10.2 mg/dL 9.10
    Test | Result | Unit | Range     e.g.  CALCIUM 9.10 mg/dL 8.4 - 10.2
    Test | Result | Range | Unit     e.g.  CALCIUM 9.10 8.4 - 10.2 mg/dL
The test name may also be on the line ABOVE the numbers, as in many PDFs:
    VITAMIN D 25 - HYDROXY, SERUM
    nmol/L 75.00 - 250.00 52.95
Ranges may be "low - high", "< 200" or "> 40".
"""

import re
import unicodedata

# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

# A standalone number: not glued to letters, dots, slashes or dashes
# (so "B12", "01/10/2026" and "123-456" are not read as results).
NUM = r"(?<![\w./-])\d+(?:\.\d+)?(?![\w./])"

# A unit: anything with a slash (mg/dL, nmol/L, 10^3/uL, mm/hr ...)
# or one of the common units without a slash.
UNIT = (
    r"(?:[^\s\d,:()][^\s,:()]*/[^\s,:()]+"
    r"|10\^\d+/[^\s,:()]+"
    r"|%|fL|fl|pg|g%|mEq|IU|U|ratio|Ratio|cells|lakhs|million)"
)

# A reference range: "8.4 - 10.2", "< 200", "> 40", "Less than 200", "Upto 5"
RANGE = (
    r"(?:(?P<low>" + NUM + r")\s*-\s*(?P<high>" + NUM + r")"
    r"|(?P<lt>(?:<=?|≤|less\s+than|upto|up\s+to)\s*)(?P<ltv>" + NUM + r")"
    r"|(?P<gt>(?:>=?|≥|more\s+than|greater\s+than)\s*)(?P<gtv>" + NUM + r"))"
)

FLAG = r"(?:\s*(?P<flag>H|L|High|Low|HIGH|LOW|\*))?"

LAYOUTS = [
    # Test | Unit | Range | Result
    re.compile(
        r"^(?P<name>.*?)\s*(?P<unit>" + UNIT + r")\s+" + RANGE
        + r"\s+(?P<result>" + NUM + r")" + FLAG + r"\s*$",
        re.IGNORECASE,
    ),
    # Test | Range | Unit | Result
    re.compile(
        r"^(?P<name>.*?)\s*" + RANGE + r"\s+(?P<unit>" + UNIT + r")"
        r"\s+(?P<result>" + NUM + r")" + FLAG + r"\s*$",
        re.IGNORECASE,
    ),
    # Test | Result | Unit | Range
    re.compile(
        r"^(?P<name>.*?)\s*(?P<result>" + NUM + r")" + FLAG
        + r"\s+(?P<unit>" + UNIT + r")\s+" + RANGE + r"\s*$",
        re.IGNORECASE,
    ),
    # Test | Result | Range | Unit
    re.compile(
        r"^(?P<name>.*?)\s*(?P<result>" + NUM + r")" + FLAG
        + r"\s+" + RANGE + r"\s+(?P<unit>" + UNIT + r")\s*$",
        re.IGNORECASE,
    ),
    # Test | Range | Result  (no unit printed)
    re.compile(
        r"^(?P<name>.*?)\s*" + RANGE
        + r"\s+(?P<result>" + NUM + r")" + FLAG + r"\s*$",
        re.IGNORECASE,
    ),
]

# Lines that are never a test name
SKIP_NAME = re.compile(
    r"^\s*$"
    r"|^(test\s*name|investigation|parameter|result|units?|reference|biological|method|specimen|sample)\b"
    r"|^(page|patient|name|age|sex|gender|dob|date|lab\s*no|ref\.?\s*by|collected|reported|registered)\b"
    r"|^(interpretation|note|comments?|remarks?|end\s+of\s+report)\b"
    r"|^[\W\d_]+$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# "low - high+result" where high and result are stuck together, e.g.
# "8.4 - 10.29.10" or "75.00 - 250.0052.95". The second number contains
# two decimal points, which no real number has.
_GLUED_RANGE = re.compile(
    r"(?<![\w.])(?P<low>\d+\.(?P<dec>\d+)) - (?P<glued>\d+\.\d+\.\d+)(?![\w.])"
)


def _split_glued_range(match):
    """Split the glued part using the low value's number of decimals.

    The range end usually has the same number of decimals as the range start
    (8.4 - 10.2, 75.00 - 250.00), so "10.29.10" -> "10.2" + "9.10".
    """
    low, decimals, glued = match.group("low"), len(match.group("dec")), match.group("glued")
    whole, rest = glued.split(".", 1)
    high = f"{whole}.{rest[:decimals]}"
    result = rest[decimals:]
    if not re.fullmatch(r"\d+\.\d+", result):
        return match.group(0)  # unsure, leave the text unchanged
    if float(low) >= float(high):
        return match.group(0)
    return f"{low} - {high} {result}"


def normalize_text(text):
    """Clean up Unicode, dashes and spacing so the patterns match reliably."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    # All dash-like characters become a normal hyphen
    text = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uFE58\uFE63\uFF0D]", "-", text)
    # Micro sign variants become "u" so units like uIU/mL are consistent
    text = text.replace("\u00b5", "u").replace("\u03bc", "u")
    # Tabs, non-breaking spaces etc. become normal spaces
    text = re.sub(r"[\t\u00a0\u2000-\u200b\u202f\u205f\u3000]", " ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # "8.4-10.2" or "8.4 -10.2" become "8.4 - 10.2"
    text = re.sub(r"(\d)\s*-\s*(\d)", r"\1 - \2", text)
    # Some PDFs glue the range end and the result together:
    # "8.4 - 10.29.10" -> "8.4 - 10.2 9.10"
    text = _GLUED_RANGE.sub(_split_glued_range, text)
    # Collapse repeated spaces on each line
    lines = [re.sub(r" {2,}", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines)


def _clean_name(name):
    name = re.sub(r"\s+", " ", name or "").strip(" :-|")
    # Remove a trailing method in brackets, e.g. "CALCIUM (Arsenazo)"
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip(" :-|")
    return name


def _looks_like_name(line):
    if SKIP_NAME.search(line):
        return False
    if len(line) > 80:
        return False
    letters = sum(ch.isalpha() for ch in line)
    return letters >= 2


def _find_name_above(lines, index):
    """Look up to 3 lines above a numbers-only row for its test name."""
    for back in range(1, 4):
        j = index - back
        if j < 0:
            break
        candidate = lines[j].strip()
        if not candidate:
            continue
        if any(p.match(candidate) for p in LAYOUTS):
            break  # reached the previous test's row
        # Skip method lines such as "(Arsenazo III)" or "(CLIA)"
        if candidate.startswith("(") and candidate.endswith(")"):
            continue
        cleaned = _clean_name(candidate)
        if cleaned and _looks_like_name(cleaned):
            return cleaned
    return ""


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _status(value, low, high):
    if low is not None and value < low:
        return "LOW"
    if high is not None and value > high:
        return "HIGH"
    return "NORMAL"


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def analyze_lab_values(text):
    """Extract lab results with reference ranges from report text."""
    clean = normalize_text(text)
    lines = clean.split("\n")
    results = []
    seen = set()

    for i, line in enumerate(lines):
        if not line or not re.search(r"\d", line):
            continue

        match = None
        for pattern in LAYOUTS:
            match = pattern.match(line)
            if match:
                break
        if not match:
            continue

        g = match.groupdict()
        value = _to_float(g.get("result"))
        if value is None:
            continue

        low = high = None
        if g.get("low") is not None:
            low, high = _to_float(g["low"]), _to_float(g["high"])
            if low is None or high is None or low >= high:
                continue  # not a real range (e.g. part of a date or ID)
            range_text = f"{g['low']} - {g['high']}"
        elif g.get("ltv") is not None:
            high = _to_float(g["ltv"])
            range_text = f"< {g['ltv']}"
        elif g.get("gtv") is not None:
            low = _to_float(g["gtv"])
            range_text = f"> {g['gtv']}"
        else:
            continue

        name = _clean_name(g.get("name"))
        if not name or not _looks_like_name(name):
            name = _find_name_above(lines, i)
        if not name:
            continue

        key = (name.lower(), g["result"])
        if key in seen:
            continue
        seen.add(key)

        results.append({
            "test": name,
            "value": value,
            "value_text": g["result"],
            "unit": (g.get("unit") or "").strip(),
            "reference_range": range_text,
            "low": low,
            "high": high,
            "status": _status(value, low, high),
        })

    return results


# ---------------------------------------------------------------------------
# Quick self-test:  python -m backend.lab_analyzer
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample = """
Patient Name : Test Patient      Age : 34 Years
Lab No. : 123456789   Date : 01/10/2026
Test Name Units Bio. Ref. Interval Results
CALCIUM, SERUM
(Arsenazo III)
mg/dL 8.4 - 10.2 9.10
VITAMIN D 25 - HYDROXY, SERUM
(CLIA)
nmol/L 75.00 \u2013 250.00 52.95
Deficient : < 50 nmol/L
Page 1 of 2
"""
    for row in analyze_lab_values(sample):
        print(f"{row['test']}: {row['value_text']} {row['unit']} "
              f"(ref {row['reference_range']}) -> {row['status']}")