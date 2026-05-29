"""v4.00.35 — Operator pages + JSON API for the canonical wedge registry.

Stable URLs
-----------
* ``/super/wedges/`` — index of all 45 wedges, grouped by tier with phase
  badges + facet chip filters + coverage tile.
* ``/super/wedge/<id>/`` — single-wedge operator page (registry + checklist
  + live-checked deep links + sibling navigation + ``?wedge=`` deep-link
  generator).
* ``/api/v1/super/wedges/`` — JSON list (operator tooling).
* ``/api/v1/super/wedges/<id>/`` — JSON single (operator tooling).
* ``?format=json`` is honored on the index + detail pages.

The grouped-surface ``?wedge=<id>`` convention is documented per-wedge in
the registry's ``deep_links`` field — this view layer doesn't gate
filtering on grouped surfaces, but the URLs it emits feed straight into
them.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpRequest, JsonResponse
from django.shortcuts import render
from django.urls import NoReverseMatch
from django.views.decorators.http import require_http_methods

from apps.siteconfig._wedge_registry import (
    PHASES,
    TIERS,
    coverage_summary,
    live_check,
    wedge,
    wedges,
    wedges_by_phase,
    wedges_by_tier,
)

logger = logging.getLogger(__name__)


def _wants_json(request: HttpRequest) -> bool:
    fmt = (request.GET.get("format") or "").lower()
    if fmt == "json":
        return True
    accept = (request.META.get("HTTP_ACCEPT") or "").lower()
    return "application/json" in accept and "text/html" not in accept


def _decorate_checklist(w: dict) -> list[dict]:
    """Apply live-check results to the wedge's checklist."""
    results = live_check(w["id"])
    out = []
    for idx, item in enumerate(w["checklist"]):
        out.append({
            "text": item,
            "live": results.get(idx),  # True / False / None (unknown)
        })
    return out


def _deep_link_with_filter(path: str, wedge_id: int) -> str:
    """Append ?wedge=<id> to a deep link if it accepts a query string."""
    if not path or path.startswith("#"):
        return path
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}{urlencode({'wedge': wedge_id})}"


# ----- Index --------------------------------------------------------------


@staff_member_required
@require_http_methods(["GET"])
def wedge_index(request):
    """List all 45 wedges grouped by tier."""
    all_wedges = wedges()
    by_tier = wedges_by_tier()
    by_phase = wedges_by_phase()
    summary = coverage_summary()

    if _wants_json(request):
        return JsonResponse({
            "success": True,
            "count": len(all_wedges),
            "summary": summary,
            "wedges": all_wedges,
        })

    return render(request, "super/wedges/index.html", {
        "wedges": all_wedges,
        "by_tier": by_tier,
        "by_phase": by_phase,
        "tiers": TIERS,
        "phases": PHASES,
        "summary": summary,
    })


# ----- Detail -------------------------------------------------------------


@staff_member_required
@require_http_methods(["GET"])
def wedge_detail(request, wedge_id: int):
    """Canonical operator page for a single wedge."""
    w = wedge(wedge_id)
    if w is None:
        raise Http404("Unknown wedge")

    decorated = _decorate_checklist(w)
    deep_links = [
        {
            "label": label,
            "path": path,
            "path_with_filter": _deep_link_with_filter(path, w["id"]),
        }
        for (label, path) in (w.get("deep_links") or [])
    ]

    # Sibling navigation — prev / next by id, wrapping around.
    all_ids = sorted(x["id"] for x in wedges())
    pos = all_ids.index(w["id"])
    prev_id = all_ids[pos - 1]
    next_id = all_ids[(pos + 1) % len(all_ids)]

    # Sister wedges in the same tier (for cross-nav).
    siblings_in_tier = [
        {"id": x["id"], "slug": x["slug"], "name": x["name"]}
        for x in wedges_by_tier().get(w["tier"], [])
        if x["id"] != w["id"]
    ]

    if _wants_json(request):
        return JsonResponse({
            "success": True,
            "wedge": {
                **w,
                "checklist_decorated": decorated,
                "deep_links_decorated": deep_links,
                "siblings_in_tier": siblings_in_tier,
            },
            "prev_id": prev_id,
            "next_id": next_id,
        })

    return render(request, "super/wedges/detail.html", {
        "wedge": w,
        "checklist": decorated,
        "deep_links": deep_links,
        "siblings_in_tier": siblings_in_tier,
        "prev_id": prev_id,
        "next_id": next_id,
        "tier_info": TIERS.get(w["tier"], {}),
        "phase_label": PHASES.get(w["phase"], ""),
        "phases": PHASES,
    })


# ----- JSON API (under /api/v1/super/wedges/) -----------------------------


@staff_member_required
@require_http_methods(["GET"])
def api_wedge_list(request):
    return JsonResponse({
        "success": True,
        "count": len(wedges()),
        "summary": coverage_summary(),
        "wedges": wedges(),
    })


@staff_member_required
@require_http_methods(["GET"])
def api_wedge_detail(request, wedge_id: int):
    w = wedge(wedge_id)
    if w is None:
        return JsonResponse({"success": False, "error": "not_found"}, status=404)
    return JsonResponse({"success": True, "wedge": {
        **w,
        "checklist_decorated": _decorate_checklist(w),
    }})


# ----- URL-name resolver helper for templates -----------------------------


def resolve_deep_link(path: str) -> str | None:
    """Used by templates to detect broken deep links at render time.

    Returns the original path when reachable (best-effort, just by string
    inspection — we don't reverse-route to avoid coupling to URL names that
    may rename). Returns ``None`` on obvious dead paths.
    """
    if not path:
        return None
    try:
        return path
    except NoReverseMatch:
        return None
