"""Pre-processor for already-exported Veracross CSV. Does NOT touch network or SIS auth — pure data transform.

Rules (v3.38.0): mirrors ``companion-tauri/src-tauri/src/extractors/veracross.rs``.
"""
from __future__ import annotations

from typing import Optional

from . import normalize_header


def preprocess_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [_preprocess_row(r) for r in rows]


def _detect_role(row: dict[str, str]) -> str:
    for k, v in row.items():
        nk = normalize_header(k)
        if nk in ("role", "person_type", "constituent_type"):
            lv = v.strip().lower()
            if lv == "student":
                return "student"
            if lv == "faculty":
                return "faculty"
            if lv == "staff":
                return "staff"
            if lv in ("parent", "guardian"):
                return "parent"
            return "unknown"
    return "unknown"


def _role_prefix_strip(norm: str) -> Optional[tuple[str, str]]:
    for p in ("student", "faculty", "staff", "parent"):
        if norm.startswith(p):
            rest = norm[len(p):].lstrip("_")
            if rest:
                return (p, rest)
    return None


def _preprocess_row(row: dict[str, str]) -> dict[str, str]:
    role = _detect_role(row)
    out: dict[str, str] = {}
    for raw_k, v in row.items():
        norm = normalize_header(raw_k)

        # Role-partitioned columns.
        stripped = _role_prefix_strip(norm)
        if stripped is not None:
            prefix, suffix = stripped
            matches = (
                (prefix == "student" and role == "student")
                or (prefix == "faculty" and role == "faculty")
                or (prefix == "staff" and role == "staff")
                or (prefix == "parent" and role == "parent")
            )
            if matches:
                canonical = {
                    "email": "email",
                    "phone": "phone",
                    "firstname": "first_name",
                    "lastname": "last_name",
                }.get(suffix, suffix)
                out[canonical] = v
            else:
                # preserve under normalized key
                out[norm] = v
            continue

        if norm in ("person_id", "person_pk"):
            if role in ("faculty", "staff"):
                out["staff_external_id"] = v
            elif role == "parent":
                out["guardian_external_id"] = v
            else:
                out["external_id"] = v
        elif norm in ("first_name", "firstname"):
            out["first_name"] = v
        elif norm in ("last_name", "lastname"):
            out["last_name"] = v
        elif norm in ("sex", "gender"):
            out["gender"] = v.strip()
        elif norm in ("current_grade", "grade_level", "grade"):
            out["grade_level"] = v
        elif norm in ("grad_year", "graduation_year"):
            out["graduation_year"] = v
        elif norm in ("birth_date", "birthdate", "date_of_birth", "dob"):
            out["date_of_birth"] = _normalize_slash_date(v)
        elif norm == "enrollment_date":
            out["enrollment_date"] = _normalize_slash_date(v)
        elif norm == "household_id":
            out["household_id"] = v
        else:
            out[norm] = v
    return out


def _normalize_slash_date(s: str) -> str:
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
