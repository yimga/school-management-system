"""
Batch 14: map siteconfig typed EAV DynamicField* ↔ metadata JSON DynamicField*.

Pure functions only (no DB). See docs/BATCH_14_DYNAMICFIELD_RECONCILIATION.md.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

# Legacy siteconfig typed EAV codes (TEXT, NUMBER, …) → metadata lowercase codes
SITECONFIG_DATA_TYPE_TO_METADATA: dict[str, str] = {
    "TEXT": "string",
    "NUMBER": "number",
    "DATE": "date",
    "BOOLEAN": "boolean",
    "JSON": "json",
}

METADATA_DATA_TYPE_TO_SITECONFIG: dict[str, str] = {
    v: k for k, v in SITECONFIG_DATA_TYPE_TO_METADATA.items()
}


def siteconfig_definition_data_type_to_metadata(data_type: str) -> str:
    key = (data_type or "").strip().upper()
    return SITECONFIG_DATA_TYPE_TO_METADATA.get(key, "string")


def metadata_definition_data_type_to_siteconfig(data_type: str) -> str:
    key = (data_type or "").strip().lower()
    return METADATA_DATA_TYPE_TO_SITECONFIG.get(key, "TEXT")


def siteconfig_value_to_metadata_value_json(
    *,
    siteconfig_data_type: str,
    value_text: str = "",
    value_number: Any = None,
    value_date: Any = None,
    value_json: Any = None,
) -> dict[str, Any]:
    """
    Build metadata ``value_json`` envelope ``{"v": ...}`` from siteconfig typed columns.

    BOOLEAN: prefers ``value_json`` if truthy dict/scalar; else parses ``value_text``.
    """
    dt = (siteconfig_data_type or "").strip().upper()
    if dt == "TEXT":
        return {"v": value_text or ""}
    if dt == "NUMBER":
        if value_number is None:
            return {"v": None}
        if isinstance(value_number, Decimal):
            return {"v": float(value_number)}
        return {"v": value_number}
    if dt == "DATE":
        if value_date is None:
            return {"v": None}
        if isinstance(value_date, date):
            return {"v": value_date.isoformat()}
        return {"v": str(value_date)}
    if dt == "BOOLEAN":
        if value_json is not None and value_json != {}:
            if isinstance(value_json, dict) and "v" in value_json:
                return {"v": bool(value_json.get("v"))}
            return {"v": bool(value_json)}
        raw = (value_text or "").strip().lower()
        if raw in ("1", "true", "yes", "on"):
            return {"v": True}
        if raw in ("0", "false", "no", "off", ""):
            return {"v": False}
        return {"v": False}
    if dt == "JSON":
        if value_json is not None:
            return {"v": value_json}
        return {"v": {}}
    return {"v": value_text or ""}


def metadata_value_json_to_siteconfig_columns(
    *,
    metadata_data_type: str,
    value_json: Any,
) -> dict[str, Any]:
    """
    Produce kwargs-shaped dict for siteconfig ``DynamicFieldValue`` typed columns
    from metadata ``value_json`` (unwrap ``{"v": ...}``).
    """
    meta_dt = (metadata_data_type or "").strip().lower()
    payload = value_json
    if isinstance(value_json, dict) and set(value_json.keys()) == {"v"}:
        payload = value_json.get("v")

    out: dict[str, Any] = {
        "value_text": "",
        "value_number": None,
        "value_date": None,
        "value_json": None,
    }
    if meta_dt == "string":
        out["value_text"] = "" if payload is None else str(payload)
    elif meta_dt == "number":
        out["value_number"] = None if payload is None else payload
    elif meta_dt == "date":
        if payload is None:
            out["value_date"] = None
        elif isinstance(payload, date):
            out["value_date"] = payload
        else:
            s = str(payload).strip()
            try:
                out["value_date"] = date.fromisoformat(s)
            except ValueError:
                out["value_text"] = s
    elif meta_dt == "boolean":
        out["value_text"] = "true" if bool(payload) else "false"
    elif meta_dt == "json":
        out["value_json"] = payload if payload is not None else {}
    else:
        out["value_text"] = "" if payload is None else str(payload)
    return out
