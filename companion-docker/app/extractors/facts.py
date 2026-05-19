"""Pre-processor for already-exported FACTS CSV. Does NOT touch network or SIS auth — pure data transform.

Rules (v3.38.0): mirrors ``companion-tauri/src-tauri/src/extractors/facts.rs``.

ASPX-exported CSV from FACTS typically uses tab separator and \\r\\n
line endings; separator handling is the upstream parser's job. This
module trims stray \\r from cell values defensively.

Write-path fields (status, balance) are routed to ``read_only_``
prefixed keys per the v3.34.0 FACTS counsel docket
(# honest-stub: write-path counsel-blocked).
"""
from __future__ import annotations

from . import normalize_header


def preprocess_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [_preprocess_row(r) for r in rows]


def _preprocess_row(row: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_k, v in row.items():
        norm = normalize_header(raw_k)
        value = v.rstrip("\r") if v is not None else ""

        if norm in ("familyid", "family_id"):
            out["household_id"] = value
        elif norm in ("personid", "person_id"):
            out["external_id"] = value
        elif norm in ("studentid", "student_id"):
            out["student_external_id"] = value
        elif norm in ("firstname", "first_name"):
            out["first_name"] = value
        elif norm in ("lastname", "last_name"):
            out["last_name"] = value
        elif norm in ("middlename", "middle_name"):
            out["middle_name"] = value
        elif norm in ("email", "emailaddress"):
            out["email"] = value
        elif norm in ("phone", "phonenumber"):
            out["phone"] = value
        elif norm in ("dob", "birthdate", "date_of_birth"):
            out["date_of_birth"] = _normalize_short_year_date(value)
        elif norm in ("enrollmentdate", "enrollment_date"):
            out["enrollment_date"] = _normalize_short_year_date(value)
        # honest-stub: write-path counsel-blocked
        elif norm in ("tuition_balance", "balance"):
            out["read_only_balance"] = value
        # honest-stub: write-path counsel-blocked
        elif norm in ("enrollmentstatus", "enrollment_status", "status"):
            out["read_only_status"] = value
        elif norm in ("grade", "grade_level", "gradelevel"):
            out["grade_level"] = value
        else:
            out[norm] = value
    return out


def _normalize_short_year_date(s: str) -> str:
    if s is None:
        return ""
    t = s.strip()
    if not t:
        return ""
    parts = t.split("/")
    if len(parts) != 3:
        return t
    m, d, y = parts
    if not (m.isdigit() and d.isdigit() and y.isdigit()):
        return t
    try:
        mi, di, yi = int(m), int(d), int(y)
    except ValueError:
        return t
    if not (1 <= mi <= 12 and 1 <= di <= 31):
        return t
    if len(y) == 2:
        full = 2000 + yi if yi <= 49 else 1900 + yi
    elif len(y) == 4:
        full = yi
    else:
        return t
    return f"{full:04d}-{mi:02d}-{di:02d}"
