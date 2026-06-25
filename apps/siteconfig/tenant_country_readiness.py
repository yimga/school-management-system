"""250-country readiness context for tenant experience scoring."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.siteconfig.country_experience_baselines import baseline_index

_ROOT = Path(__file__).resolve().parents[2]
_MATRIX_PATH = _ROOT / "docs" / "generated" / "tenant_customer_250_country_matrix.json"

# Tier bonus when policy ``experience_score_country_bonus`` is 0 (auto mode).
READINESS_STATUS_BONUS: dict[str, int] = {
    "repo_ready": 10,
    "education_model_ready": 8,
    "localization_ready": 7,
    "configuration_ready": 6,
    "internal_pilot_ready": 5,
    "external_validation_required": 4,
    "regional_fallback_only": 3,
}

_DEFAULT_BASELINE_BONUS = 5


@lru_cache(maxsize=1)
def _matrix_index() -> dict[str, str]:
    if not _MATRIX_PATH.is_file():
        return {}
    try:
        payload = json.loads(_MATRIX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    out: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        iso = str(row.get("iso") or "").strip().upper()
        status = str(row.get("readiness_status") or "").strip().lower()
        if len(iso) == 2 and status:
            out[iso] = status
    return out


def _first_attr(*objects: Any, names: tuple[str, ...]) -> str:
    for obj in objects:
        if obj is None:
            continue
        for name in names:
            value = getattr(obj, name, None)
            if value:
                return str(value).strip()
    return ""


def school_country_code(request: HttpRequest | None) -> str:
    if request is None:
        return ""
    school = getattr(request, "school", None)
    site = getattr(request, "site_settings", None) or getattr(request, "SITE", None)
    code = _first_attr(
        school,
        site,
        names=("country_code", "country", "default_country", "region"),
    )
    return code[:2].upper() if len(code) >= 2 else ""


def country_readiness_context(request: HttpRequest | None) -> dict[str, Any]:
    """Resolved country rails + 250-country matrix tier for scoring."""
    code = school_country_code(request)
    baseline = baseline_index().get(code) if code else None
    matrix_status = _matrix_index().get(code) if code else ""
    configured = bool(code and (baseline is not None or matrix_status))
    if baseline is not None:
        return {
            "configured": True,
            "country_code": code,
            "readiness_status": matrix_status or "baseline_catalog",
            "label": f"{baseline.label} ({baseline.country_code})",
            "detail": str(
                _("%(currency)s with %(rail)s primary rail")
                % {"currency": baseline.currency, "rail": baseline.primary_rail}
            ),
            "currency": baseline.currency,
            "rail": baseline.primary_rail,
            "auto_bonus": _bonus_for_status(matrix_status or "baseline_catalog"),
        }
    if matrix_status:
        return {
            "configured": True,
            "country_code": code,
            "readiness_status": matrix_status,
            "label": str(_("%(code)s — global readiness tier") % {"code": code}),
            "detail": str(
                _("Country set — unlock local currency rails in School Studio.")
            ),
            "currency": "",
            "rail": "",
            "auto_bonus": _bonus_for_status(matrix_status),
        }
    return {
        "configured": False,
        "country_code": "",
        "readiness_status": "",
        "label": str(_("Global baseline")),
        "detail": str(_("Set country to unlock local currency and payment rails.")),
        "currency": "",
        "rail": "",
        "auto_bonus": 0,
    }


def _bonus_for_status(status: str) -> int:
    normalized = str(status or "").strip().lower()
    if normalized == "baseline_catalog":
        return _DEFAULT_BASELINE_BONUS
    return READINESS_STATUS_BONUS.get(normalized, _DEFAULT_BASELINE_BONUS)


def resolve_effective_country_bonus(
    policy: dict[str, Any],
    *,
    country_ctx: dict[str, Any],
) -> int:
    """Explicit policy bonus wins; else auto tier bonus when country is configured."""
    explicit = int(policy.get("experience_score_country_bonus", 0) or 0)
    if explicit > 0:
        return explicit
    if not country_ctx.get("configured"):
        return 0
    return int(country_ctx.get("auto_bonus") or 0)


__all__ = [
    "READINESS_STATUS_BONUS",
    "country_readiness_context",
    "resolve_effective_country_bonus",
    "school_country_code",
]
