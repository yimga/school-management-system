"""Pre-processor for already-exported Alma CSV. Does NOT touch network or SIS auth — pure data transform.

Rules (v3.38.0): mirrors ``companion-tauri/src-tauri/src/extractors/alma.rs``.
"""
from __future__ import annotations

import json
from typing import Optional

from . import normalize_header


def preprocess_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [_preprocess_row(r) for r in rows]


def _preprocess_row(row: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_k, v in row.items():
        norm = normalize_header(raw_k)
        value = _denull(v)

        if norm in ("alma_id", "school_users_id"):
            out["external_id"] = value
        elif norm == "user_type":
            out["role"] = value
        elif norm in ("first_name", "firstname"):
            out["first_name"] = value
        elif norm in ("last_name", "lastname"):
            out["last_name"] = value
        elif norm == "email":
            out["email"] = value
        elif norm == "phone":
            out["phone"] = value
        elif norm in ("extra_attributes", "custom_fields_json", "graphql_node"):
            flattened = _flatten_json_one_level(value)
            if flattened is None:
                out[norm] = value
            else:
                for k, v2 in flattened:
                    out.setdefault(k, v2)
        else:
            out[norm] = value
    return out


def _denull(s: str) -> str:
    if s is None:
        return ""
    t = s.strip()
    if not t:
        return ""
    if t.lower() == "null":
        return ""
    return s


def _flatten_json_one_level(s: str) -> Optional[list[tuple[str, str]]]:
    """Parse a JSON object and flatten one level. Returns ``None`` when
    the input is not a parseable JSON object."""
    if s is None:
        return None
    t = s.strip()
    if not t:
        return None
    try:
        parsed = json.loads(t)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    out: list[tuple[str, str]] = []
    # Sorted for deterministic output.
    for k in sorted(parsed.keys()):
        raw = parsed[k]
        if raw is None:
            sv = ""
        elif isinstance(raw, str):
            sv = raw
        elif isinstance(raw, bool):
            # bool is a subtype of int — render as "true"/"false"
            sv = "true" if raw else "false"
        elif isinstance(raw, (int, float)):
            sv = repr(raw) if isinstance(raw, float) else str(raw)
        else:
            sv = json.dumps(raw, sort_keys=True, ensure_ascii=False)
        out.append((normalize_header(k), sv))
    return out
