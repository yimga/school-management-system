"""Library inventory wizard → loan policy + barcode scheme (in-repo models)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _library_settings(school: Any) -> dict[str, Any]:
    return dict((getattr(school, "settings", None) or {}).get("library") or {})


def _save_library(school: Any, lib: dict[str, Any]) -> None:
    lib["updated_at"] = _utc_now()
    settings = dict(getattr(school, "settings", None) or {})
    settings["library"] = lib
    school.settings = settings
    school.save(update_fields=["settings"])


def _dec(value: Any, default: str = "0.00") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def configure_catalog_policy(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    lib = _library_settings(school)
    lib["catalog"] = {
        "default_loan_period_days": int(payload.get("default_loan_period_days") or 14),
        "max_concurrent_loans_per_student": int(payload.get("max_concurrent_loans_per_student") or 3),
        "renewals_allowed": int(payload.get("renewals_allowed") or 1),
    }
    _save_library(school, lib)
    return {"ok": True, "catalog": lib["catalog"]}


def configure_fine_policy(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    lib = _library_settings(school)
    lib["fines"] = {
        "fine_per_day_overdue_decimal": str(_dec(payload.get("fine_per_day_overdue_decimal"), "0.50")),
        "grace_period_days": int(payload.get("grace_period_days") or 0),
        "max_fine_per_book_decimal": str(_dec(payload.get("max_fine_per_book_decimal"), "25.00")),
        "suspend_after_unpaid_fine_days": int(payload.get("suspend_after_unpaid_fine_days") or 30),
    }
    _save_library(school, lib)
    return {"ok": True, "fines": lib["fines"]}


def configure_categories(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    categories = payload.get("value") or payload.get("categories") or []
    if not isinstance(categories, list):
        categories = [categories]
    lib = _library_settings(school)
    lib["categories"] = categories
    _save_library(school, lib)
    return {"ok": True, "categories": categories}


def configure_barcode_scheme(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    scheme = payload.get("value") or payload.get("barcode_scheme") or "isbn13"
    lib = _library_settings(school)
    lib["barcode_scheme"] = str(scheme)
    _save_library(school, lib)
    return {"ok": True, "barcode_scheme": lib["barcode_scheme"]}
