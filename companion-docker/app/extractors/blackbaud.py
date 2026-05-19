"""Pre-processor for already-exported Blackbaud CSV. Does NOT touch network or SIS auth — pure data transform.

Rules (v3.38.0): mirrors ``companion-tauri/src-tauri/src/extractors/blackbaud.rs``.
"""
from __future__ import annotations

from . import normalize_header


def preprocess_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [_preprocess_row(r) for r in rows]


def _preprocess_row(row: dict[str, str]) -> dict[str, str]:
    is_guardian_row = any(
        normalize_header(k) == "relationshiptype" for k in row.keys()
    )
    out: dict[str, str] = {}
    for raw_k, v in row.items():
        norm = normalize_header(raw_k)
        canonical = _map_header(norm, is_guardian_row)
        if canonical == "external_id":
            out["external_id"] = v
        elif canonical == "guardian_external_id":
            out["guardian_external_id"] = v
        elif canonical == "student_external_id":
            out["student_external_id"] = v
        elif canonical == "first_name":
            out["first_name"] = v
        elif canonical == "last_name":
            out["last_name"] = v
        elif canonical == "middle_name":
            out["middle_name"] = v
        elif canonical == "email":
            out["email"] = v
        elif canonical == "phone":
            out["phone"] = v
        elif canonical == "date_of_birth":
            out["date_of_birth"] = _truncate_iso(v)
        elif canonical == "enrollment_date":
            out["enrollment_date"] = _truncate_iso(v)
        elif canonical == "exit_date":
            out["exit_date"] = _truncate_iso(v)
        elif canonical == "guardian_relationship":
            out["guardian_relationship"] = _normalize_rel(v)
        elif canonical == "grade_level":
            out["grade_level"] = v
        elif canonical == "gender":
            out["gender"] = v.strip()
        else:
            out[norm] = v
    return out


def _map_header(norm: str, is_guardian_row: bool) -> str:
    if norm in ("student_firstname", "first_name", "firstname"):
        return "first_name"
    if norm in ("student_lastname", "last_name", "lastname"):
        return "last_name"
    if norm in ("student_middlename", "middle_name", "middlename"):
        return "middle_name"
    if norm == "student_id":
        return "external_id"
    if norm in ("user_id", "constituent_id", "host_id"):
        return "guardian_external_id" if is_guardian_row else "external_id"
    if norm == "student_external_id":
        return "student_external_id"
    if norm in ("student_email", "user_email", "email"):
        return "email"
    if norm in ("student_phone", "user_phone", "phone"):
        return "phone"
    if norm in ("student_dateofbirth", "dateofbirth", "date_of_birth"):
        return "date_of_birth"
    if norm in ("enrollmentdate", "enrollment_date"):
        return "enrollment_date"
    if norm in ("exitdate", "exit_date"):
        return "exit_date"
    if norm == "relationshiptype":
        return "guardian_relationship"
    if norm in ("student_gradelevel", "grade_level", "gradelevel"):
        return "grade_level"
    if norm in ("student_gender", "gender"):
        return "gender"
    return "_passthrough"


def _truncate_iso(s: str) -> str:
    if s is None:
        return ""
    t = s.strip()
    if not t:
        return ""
    # Cut at first T or space.
    cut_at = None
    for sep in ("T", " "):
        i = t.find(sep)
        if i >= 0 and (cut_at is None or i < cut_at):
            cut_at = i
    candidate = t[:cut_at] if cut_at is not None else t
    parts = candidate.split("-")
    if len(parts) != 3 or len(parts[0]) != 4:
        return t
    if not all(p.isdigit() for p in parts):
        return t
    return candidate


_KNOWN_RELS = {
    "mother",
    "father",
    "guardian",
    "stepmother",
    "stepfather",
    "grandmother",
    "grandfather",
    "aunt",
    "uncle",
}


def _normalize_rel(s: str) -> str:
    t = s.strip()
    low = t.lower()
    if low in _KNOWN_RELS:
        return low
    return t
