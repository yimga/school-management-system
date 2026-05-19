"""Pre-processor for already-exported PowerSchool CSV. Does NOT touch network or SIS auth — pure data transform.

Rules (v3.38.0): mirrors ``companion-tauri/src-tauri/src/extractors/powerschool.rs``.
"""
from __future__ import annotations

from . import normalize_header


def preprocess_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [_preprocess_row(r) for r in rows]


def _preprocess_row(row: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_k, v in row.items():
        norm = normalize_header(raw_k)
        if norm == "student_number":
            out["external_id"] = v
        elif norm == "lastfirst":
            # "Lastname, Firstname"
            parts = v.split(",", 1)
            if len(parts) == 2:
                out["last_name"] = parts[0].strip()
                out["first_name"] = parts[1].strip()
            else:
                out["last_name"] = v.strip()
        elif norm in ("first_name", "firstname"):
            out["first_name"] = v
        elif norm in ("last_name", "lastname"):
            out["last_name"] = v
        elif norm in ("middle_name", "middlename"):
            out["middle_name"] = v
        elif norm in ("dob", "date_of_birth"):
            out["date_of_birth"] = _normalize_us_date(v)
        elif norm == "entrydate":
            out["enrollment_date"] = _normalize_us_date(v)
        elif norm == "exitdate":
            out["exit_date"] = _normalize_us_date(v)
        elif norm in ("gender", "sex"):
            out["gender"] = _normalize_gender(v)
        elif norm in ("enroll_status", "enrollment_status"):
            out["enrollment_status"] = _normalize_status(v)
        elif norm == "grade_level":
            out["grade_level"] = v
        elif norm in ("home_phone", "phone"):
            out["phone"] = v
        elif norm in ("student_email", "email"):
            out["email"] = v
        else:
            out[norm] = v
    return out


def _normalize_us_date(s: str) -> str:
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
    if len(y) != 4:
        return t
    try:
        mi, di, yi = int(m), int(d), int(y)
    except ValueError:
        return t
    if not (1 <= mi <= 12 and 1 <= di <= 31):
        return t
    return f"{yi:04d}-{mi:02d}-{di:02d}"


def _normalize_gender(s: str) -> str:
    t = s.strip().upper()
    if t in ("M", "F", "O", "U"):
        return t
    return s.strip()


def _normalize_status(s: str) -> str:
    t = s.strip().upper()
    return {
        "A": "active",
        "I": "inactive",
        "T": "transferred",
        "G": "graduated",
    }.get(t, s.strip())
