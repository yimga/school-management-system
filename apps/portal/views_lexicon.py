"""Wave F (2026-05-15): tenant lexicon settings UI.

GET  /portal/configure/lexicon/   — current overrides + live preview
POST /portal/configure/lexicon/   — save overrides (with audit log)

Stored in ``request.school.settings["terminology"]`` (the same JSON blob
the Wave A cascade reads). Each key maps to either a flat string
(singular only, plural auto-derives) or a `{"singular": ..., "plural": ...}`
dict — both shapes are accepted by ``apps.siteconfig.lexicon_catalog.normalise_override``.

Permissioned to school admins / principals only; the existing
`apps.billing.entitlements.can` gate covers feature toggling if needed.
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.siteconfig.lexicon_catalog import (
    LEXICON_REGISTRY,
    grouped_by_category,
    is_known_key,
    normalise_override,
)
from apps.siteconfig.terminology_service import resolve_all_terms

logger = logging.getLogger(__name__)


def _user_can_edit(request: HttpRequest) -> bool:
    """School admins / principals can edit; staff implicit."""
    user = request.user
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    role = (getattr(user, "role", "") or "").lower()
    return role in {"admin", "principal", "proprietor"}


def _current_overrides(school) -> dict[str, dict[str, str]]:
    raw = getattr(school, "settings", None)
    raw = raw if isinstance(raw, dict) else {}
    terms = raw.get("terminology")
    out: dict[str, dict[str, str]] = {}
    if isinstance(terms, dict):
        for key, value in terms.items():
            norm = normalise_override(value)
            if norm:
                out[key] = norm
    return out


def _save_overrides(school, overrides: dict[str, dict[str, str]]) -> None:
    base = dict(school.settings or {})
    if overrides:
        base["terminology"] = overrides
    else:
        base.pop("terminology", None)
    school.settings = base
    school.save(update_fields=["settings"])


def _collect_post(post) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Parse the form payload into a cleaned override map + a list of warnings.

    Form field naming: ``term[<key>][singular]`` / ``term[<key>][plural]``.
    Empty values mean "remove override for that key".
    """
    overrides: dict[str, dict[str, str]] = {}
    warnings: list[str] = []
    seen_keys: set[str] = set()
    for field_name, value in post.items():
        if not field_name.startswith("term[") or not field_name.endswith("]"):
            continue
        # term[student][singular]
        inner = field_name[len("term["):-1]
        if "][" not in inner:
            continue
        key, slot = inner.split("][", 1)
        if not is_known_key(key):
            warnings.append(f"Ignored unknown key: {key!r}")
            continue
        if slot not in {"singular", "plural"}:
            continue
        cleaned = (value or "").strip()
        if not cleaned:
            continue
        # Don't allow override that just restates the default — keeps storage clean.
        default_s, default_p, _cat, _desc = LEXICON_REGISTRY[key]
        if slot == "singular" and cleaned == default_s:
            continue
        if slot == "plural" and cleaned == default_p:
            continue
        slot_data = overrides.setdefault(key, {})
        slot_data[slot] = cleaned
        seen_keys.add(key)
    return overrides, warnings


@login_required
@require_http_methods(["GET", "POST"])
def lexicon_settings(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    if school is None:
        return render(request, "portal/configure/lexicon_no_tenant.html", status=400)
    if not _user_can_edit(request):
        return render(request, "portal/configure/lexicon_forbidden.html", status=403)

    if request.method == "POST":
        overrides, warnings = _collect_post(request.POST)
        _save_overrides(school, overrides)
        for w in warnings:
            messages.warning(request, w)
        messages.success(request, "Terminology saved. Pages will reflect the new wording on next reload.")
        logger.info(
            "lexicon override saved school_id=%s actor=%s keys=%s",
            school.pk, getattr(request.user, "pk", None), sorted(overrides.keys()),
        )
        return HttpResponseRedirect(reverse("portal_lexicon_settings"))

    overrides = _current_overrides(school)
    resolved = resolve_all_terms(school)  # includes defaults so the form is fully populated
    grouped = grouped_by_category()

    rows_by_category: dict[str, list[dict]] = {}
    for category, keys in grouped.items():
        rows_by_category[category] = []
        for key in keys:
            default_s, default_p, _cat, desc = LEXICON_REGISTRY[key]
            current = overrides.get(key) or {}
            rows_by_category[category].append({
                "key": key,
                "description": desc,
                "default_singular": default_s,
                "default_plural": default_p,
                "current_singular": current.get("singular", ""),
                "current_plural": current.get("plural", ""),
                "resolved_singular": resolved[key]["singular"],
                "resolved_plural": resolved[key]["plural"],
                "is_overridden": bool(current),
            })

    context = {
        "rows_by_category": rows_by_category,
        "override_count": len(overrides),
        "school": school,
    }
    return render(request, "portal/configure/lexicon_settings.html", context)
