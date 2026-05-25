"""Parse inbound page-help query params from rmc-page-context-help.js."""

from __future__ import annotations

from typing import Any


def _segment_hint(active_url: str) -> str:
    path_only = (active_url or "").split("?", 1)[0].rstrip("/")
    if not path_only:
        return ""
    segment = path_only.rsplit("/", 1)[-1]
    if not segment or segment in {"admin", "super", "portal", "kb"}:
        return ""
    return segment.replace("-", " ").replace("_", " ").strip()


def parse_help_landing_inbound(request) -> dict[str, Any]:
    """Build template context for help-center landings opened via copilot ? or topbar help."""
    q = (request.GET.get("q") or request.GET.get("title") or "").strip()
    active_url = (request.GET.get("active_url") or "").strip()[:500]
    module = (request.GET.get("module") or "").strip()[:120]
    from_page_help = request.GET.get("from") == "page_help"

    search_q = q
    if not search_q and from_page_help:
        search_q = _segment_hint(active_url)

    return {
        "page_help_active_url": active_url,
        "page_help_from_landing": from_page_help,
        "page_help_module": module,
        "help_search_initial_q": (search_q or q)[:200],
    }


def feature_form_initial_from_request(request, base: dict | None = None) -> dict[str, str]:
    """Merge page-help inbound params into FeatureRequestForm initial data."""
    merged = dict(base or {})
    inbound = parse_help_landing_inbound(request)
    if inbound["help_search_initial_q"] and not merged.get("title"):
        merged["title"] = inbound["help_search_initial_q"]
    if inbound["page_help_module"] and not merged.get("module"):
        merged["module"] = inbound["page_help_module"]
    if not merged.get("module") and inbound["page_help_active_url"]:
        merged["module"] = inbound["page_help_active_url"][:120]
    return merged
