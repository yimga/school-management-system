"""Pre-processor for already-exported Skyward CSV. Does NOT touch network or SIS auth — pure data transform.

Rules (v3.38.0): mirrors ``companion-tauri/src-tauri/src/extractors/skyward.rs``.

Skyward exports use \\r line endings (legacy Mac) and ALL_CAPS
column names. Line-ending handling is the upstream parser's job;
this module trims trailing \\r from cell values defensively.

Write-path fields (status, balance) are routed to ``read_only_``
prefixed keys per the v3.34.0 Skyward counsel docket
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

        if norm in ("skyward_id", "other_id"):
            out["external_id"] = value
        elif norm == "name_id":
            out["name_id"] = value
        elif norm == "entity_id":
            out["entity_id"] = value
        elif norm in ("first_name", "firstname", "fname"):
            out["first_name"] = value
        elif norm in ("last_name", "lastname", "lname"):
            out["last_name"] = value
        elif norm in ("middle_name", "middlename", "mname"):
            out["middle_name"] = value
        elif norm in ("email_address", "email", "email_addr"):
            out["email"] = value
        elif norm in ("phone_number", "phone"):
            out["phone"] = value
        elif norm in ("birthdate", "birth_date", "dob", "date_of_birth"):
            out["date_of_birth"] = _normalize_compact_date(value)
        elif norm in ("entry_date", "enrollment_date"):
            out["enrollment_date"] = _normalize_compact_date(value)
        elif norm in ("exit_date", "withdraw_date"):
            out["exit_date"] = _normalize_compact_date(value)
        elif norm in ("grade_level", "grade", "grad_level", "gradyr"):
            out["grade_level"] = value
        elif norm in ("gender", "sex"):
            out["gender"] = value.strip()
        elif norm == "homeroom_teacher":
            out["homeroom_teacher"] = value
        # honest-stub: write-path counsel-blocked
        elif norm in ("status", "enroll_status", "enrollment_status"):
            out["read_only_status"] = value
        # honest-stub: write-path counsel-blocked
        elif norm in ("balance", "fee_balance"):
            out["read_only_balance"] = value
        else:
            out[norm] = value
    return out


def _normalize_compact_date(s: str) -> str:
    if s is None:
        return ""
    t = s.strip()
    if not t:
        return ""
    # Already ISO?
    if len(t) == 10 and t[4] == "-" and t[7] == "-":
        return t
    if len(t) != 8 or not t.isdigit():
        return t
    try:
        y = int(t[0:4])
        m = int(t[4:6])
        d = int(t[6:8])
    except ValueError:
        return t
    if not (1 <= m <= 12 and 1 <= d <= 31):
        return t
    return f"{y:04d}-{m:02d}-{d:02d}"
