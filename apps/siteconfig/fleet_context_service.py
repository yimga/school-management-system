"""Globe-aware fleet context for copilot rail + assist dock (RBAC-gated LLM optional)."""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from django.http import HttpRequest

from apps.siteconfig.operator_fleet_snapshot import (
    build_operator_fleet_snapshot,
    rules_fleet_brief,
    rules_whisper_line,
)

logger = logging.getLogger(__name__)


def should_use_tour_narrator_llm(request: HttpRequest | None) -> bool:
    """W12 tour narrator LLM — opt-in only via ``?narrator=1`` (never default-on)."""
    if request is None:
        return False
    flag = str(request.GET.get("narrator") or "").strip().lower()
    if flag in ("0", "false", "no"):
        return False
    if flag in ("1", "true", "yes"):
        return should_use_llm_brief(request)
    return False


def rules_tour_narrator_line(
    *,
    label: str = "",
    region: str = "",
    step_index: int = 0,
    schools_live: int = 0,
) -> str:
    place = (label or region or "this region").strip()[:64]
    step = max(0, int(step_index or 0)) + 1
    return f"Stop {step} — {place}: {schools_live} live schools on the fleet map."


def build_tour_narrator_line(
    request: HttpRequest,
    *,
    label: str = "",
    region: str = "",
    lat: float | None = None,
    lng: float | None = None,
    step_index: int = 0,
    use_llm: bool = False,
) -> dict[str, Any]:
    snapshot = build_operator_fleet_snapshot()
    schools_live = int(snapshot.get("schools_live") or 0)
    line = rules_tour_narrator_line(
        label=label,
        region=region,
        step_index=step_index,
        schools_live=schools_live,
    )
    source = "rules"
    if use_llm:
        llm_line, used = _maybe_llm_tour_narrator(
            request,
            label=label,
            region=region,
            step_index=step_index,
            schools_live=schools_live,
            lat=lat,
            lng=lng,
        )
        if used:
            line = llm_line
            source = "llm"
    return {"line": line, "source": source}


def _maybe_llm_tour_narrator(
    request: HttpRequest,
    *,
    label: str,
    region: str,
    step_index: int,
    schools_live: int,
    lat: float | None,
    lng: float | None,
) -> tuple[str, bool]:
    try:
        from services.ai_helpers import invoke_with_request

        place = (label or region or "this region").strip()[:64]
        coords = ""
        if lat is not None and lng is not None:
            coords = f" Coordinates roughly {lat:.1f}, {lng:.1f}."
        prompt = (
            "Write ONE short sentence (max 120 chars) for an operator globe tour waypoint. "
            f"Place: {place}.{coords} "
            f"Fleet live schools: {schools_live}. "
            "No emails, tenant slugs, or secrets."
        )
        result = invoke_with_request(
            task_type="STUDIO_OS_ASSISTANT",
            prompt=prompt,
            request=request,
            user_query="",
            metadata={
                "northstar_prompt_type": "operator_fleet_tour_narrator",
                "content_sensitivity": "standard",
                "surface": "operator_fleet_tour_narrator",
                "rbac_scope": "operator",
                "copilot_rbac_enforced": True,
            },
        )
        if result is None:
            return rules_tour_narrator_line(
                label=label,
                region=region,
                step_index=step_index,
                schools_live=schools_live,
            ), False
        raw_text, _meta = result
        text = raw_text if isinstance(raw_text, str) else str(raw_text or "")
        line = " ".join(text.split())[:160]
        if not line:
            return rules_tour_narrator_line(
                label=label,
                region=region,
                step_index=step_index,
                schools_live=schools_live,
            ), False
        return line, True
    except Exception:
        logger.debug("fleet_context: tour narrator llm skipped", exc_info=True)
        return rules_tour_narrator_line(
            label=label,
            region=region,
            step_index=step_index,
            schools_live=schools_live,
        ), False


def should_use_llm_brief(request: HttpRequest | None) -> bool:
    """LLM brief when gateway is reachable; opt-out via ``?llm=0``."""
    if request is not None:
        llm_flag = str(request.GET.get("llm") or "").strip().lower()
        if llm_flag in ("0", "false", "no"):
            return False
        if llm_flag in ("1", "true", "yes"):
            return True
    try:
        from apps.portal.ai_provider import probe_ai_provider_reachable

        health = probe_ai_provider_reachable() or {}
    except Exception:
        return False
    if health.get("reachable"):
        return True
    posture = str(health.get("posture_mode") or "").strip().lower()
    return posture in {"live_cloud", "live_local", "guided"}


def _hash_slug(slug: str) -> str:
    if not slug:
        return ""
    return hashlib.sha256(slug.encode("utf-8")).hexdigest()[:12]


def build_fleet_context(
    request: HttpRequest,
    *,
    viewport: dict[str, Any] | None = None,
    selection: dict[str, Any] | None = None,
    use_llm_brief: bool = False,
) -> dict[str, Any]:
    """Structured fleet context — no raw slugs/emails in the default payload."""
    snapshot = build_operator_fleet_snapshot()
    lens = "operator-dashboard-fleet"
    page_root = request.GET.get("from_lens") or ""
    if hasattr(request, "resolver_match") and request.resolver_match:
        page_root = page_root or (request.path or "")

    visible_count = None
    region = (selection or {}).get("region") or (viewport or {}).get("region") or ""
    if viewport and isinstance(viewport.get("pins_in_view"), int):
        visible_count = viewport["pins_in_view"]

    whisper = rules_whisper_line(
        schools_live=int(snapshot.get("schools_live") or 0),
        suspended=int(snapshot.get("suspended") or 0),
        frozen=int(snapshot.get("frozen") or 0),
        visible_count=visible_count,
    )
    brief = snapshot.get("fleet_brief") or rules_fleet_brief(
        schools_live=int(snapshot.get("schools_live") or 0),
        suspended=int(snapshot.get("suspended") or 0),
        frozen=int(snapshot.get("frozen") or 0),
        summary_label=snapshot.get("summary_label") or "",
        pulse_events=snapshot.get("pulse_events") or [],
    )
    brief_source = "rules"

    if use_llm_brief:
        llm_brief, used_llm = _maybe_llm_brief(request, snapshot, brief)
        brief = llm_brief
        if used_llm:
            brief_source = "llm"

    sel = selection or {}
    school_slug = (sel.get("slug") or "").strip()
    ctx = {
        "lens": lens,
        "page_path": request.path or "",
        "operator_fleet_revision": snapshot.get("operator_fleet_revision"),
        "globe_revision": snapshot.get("globe_revision"),
        "viewport": viewport or {},
        "selection": {
            "region": region,
            "school_id_hash": _hash_slug(str(sel.get("school_id") or "")),
            "slug_hash": _hash_slug(school_slug),
            "status": sel.get("status") or "",
            "name_hint": (sel.get("name") or "")[:48],
        },
        "pulse_events": snapshot.get("pulse_events") or [],
        "fleet_summary": snapshot.get("fleet_summary") or {},
        "whisper_line": whisper,
        "fleet_brief": brief,
        "brief_source": brief_source,
        "school_hours_regions": snapshot.get("school_hours_regions") or 0,
        "aurora": snapshot.get("aurora") or "good",
    }
    return ctx


def _maybe_llm_brief(
    request: HttpRequest,
    snapshot: dict[str, Any],
    rules_brief: dict[str, str],
) -> tuple[dict[str, str], bool]:
    """Optional LLM brief — falls back to rules on any failure. RBAC via invoke_with_request."""
    try:
        from services.ai_helpers import invoke_with_request

        prompt = (
            "Write two short sentences for a school SaaS operator dashboard globe. "
            f"Live schools: {snapshot.get('schools_live')}. "
            f"Suspended: {snapshot.get('suspended')}. Frozen: {snapshot.get('frozen')}. "
            f"Recent pulse: {(snapshot.get('pulse_events') or [{}])[0].get('text', '')}. "
            "No emails, no full tenant names, no secrets."
        )
        result = invoke_with_request(
            task_type="STUDIO_OS_ASSISTANT",
            prompt=prompt,
            request=request,
            user_query="",
            metadata={
                "northstar_prompt_type": "operator_fleet_globe_brief",
                "content_sensitivity": "standard",
                "surface": "operator_fleet_globe_brief",
                "rbac_scope": "operator",
                "copilot_rbac_enforced": True,
            },
        )
        if result is None:
            return rules_brief, False
        raw_text, _meta = result
        text = raw_text if isinstance(raw_text, str) else str(raw_text or "")
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if not lines:
            return rules_brief, False
        headline = lines[0][:200]
        body = " ".join(lines[1:3])[:400] if len(lines) > 1 else rules_brief.get("body", "")
        return {"headline": headline, "body": body}, True
    except Exception:
        logger.debug("fleet_context: llm brief skipped", exc_info=True)
        return rules_brief, False
