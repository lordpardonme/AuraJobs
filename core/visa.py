import re
import pandas as pd

SPONSORSHIP_POSITIVE = [
    "visa sponsorship",
    "visa sponsor",
    "sponsorship available",
    "sponsorship provided",
    "work visa sponsorship",
    "employment visa sponsorship",
    "company sponsored visa",
    "company sponsorship",
    "visa support",
    "work permit sponsorship",
    "work permit support",
    "employment visa",
    "relocation and visa",
    "relocation assistance and visa",
    "visa assistance",
    "sponsor work visa",
    "sponsor your visa",
]

SPONSORSHIP_NEGATIVE = [
    "no visa sponsorship",
    "visa sponsorship not available",
    "visa sponsorship unavailable",
    "unable to sponsor",
    "cannot sponsor",
    "will not sponsor",
    "we do not sponsor",
    "does not sponsor",
    "not able to sponsor",
    "must already have the right to work",
    "must have the right to work",
    "right to work required",
    "valid work authorization required",
    "valid work permit required",
    "without sponsorship",
]

RELOCATION_TERMS = [
    "relocation assistance",
    "relocation support",
    "relocation package",
    "relocation provided",
    "relocation available",
    "relocation offered",
    "relocation assistance available",
    "relocation support available",
]

def norm_text(val):
    if val is None or pd.isna(val):
        return ""
    return re.sub(r"\s+", " ", str(val).lower()).strip()

def detect_visa_sponsorship(title: str, description: str) -> tuple:
    """Returns (status, evidence_phrase)."""
    text = norm_text(title) + " " + norm_text(description)

    for neg in SPONSORSHIP_NEGATIVE:
        if neg in text:
            return "NO SPONSORSHIP", neg

    for pos in SPONSORSHIP_POSITIVE:
        if pos in text:
            return "SPONSORSHIP MENTIONED", pos

    return "UNKNOWN", ""

def detect_relocation(title: str, description: str) -> tuple:
    """Returns (status, evidence_phrase)."""
    text = norm_text(title) + " " + norm_text(description)

    for rel in RELOCATION_TERMS:
        if rel in text:
            return "RELOCATION MENTIONED", rel

    return "UNKNOWN", ""
