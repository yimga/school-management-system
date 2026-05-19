"""
Product-tier assistants (settings, import errors, reports, guided tours).

All paths route through services.ai_gateway / engine room patterns — no direct provider imports.
"""

from __future__ import annotations

import re
from typing import Any

from services.ai.prompts import validate_response_structure
from services.ai.topology_map import search_topology

# Common bulk-import validation patterns → navigation hints (no LLM required).
_IMPORT_ERROR_HINTS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (
        re.compile(r"duplicate|already exists|unique", re.I),
        "**Data > Imports > Review duplicates**",
        "Open the import review grid and resolve or skip duplicate keys before re-uploading.",
    ),
    (
        re.compile(r"required|missing|blank|null", re.I),
        "**Data > Imports > Column mapping**",
        "Map the required column or fill mandatory fields marked with a red asterisk in the template.",
    ),
    (
        re.compile(r"invalid.*date|date.*format", re.I),
        "Use ISO dates (YYYY-MM-DD) in the template before upload.",
    ),
    (
        re.compile(r"permission|forbidden|not allowed", re.I),
        "**Settings > Roles & permissions**",
        "Your role may lack import clearance; ask a Campus Business Manager to run the import.",
    ),
    (
        re.compile(r"email|phone|format", re.I),
        "**Data > Imports > Row detail**",
        "Fix the cell format to match the validator shown in the row error panel.",
    ),
)


def _actor_roles(user: Any) -> list[str]:
    role = getattr(user, "role", None)
    if role is None:
        return []
    val = getattr(role, "value", None) or str(role)
    return [str(val)] if val else []


def smart_settings_assist(
    user: Any,
    query: str,
    *,
    school: Any | None = None,
    active_url: str = "",
) -> dict[str, Any]:
    """Natural-language settings guidance with engine-room persona + topology."""
    from services.ai.gateway import process_platform_query

    enriched = (
        f"{query.strip()}\n\n"
        "[FOCUS] SiteSettings, feature flags, theme tokens, and Configuration Control Center. "
        "Name exact menu paths; never invent setting keys."
    )
    return process_platform_query(
        user,
        active_url,
        enriched,
        school=school,
        actor_roles=_actor_roles(user),
        actor_is_staff=bool(getattr(user, "is_staff", False)),
        actor_is_superuser=bool(getattr(user, "is_superuser", False)),
    )


def resolve_import_errors(
    user: Any,
    errors: list[dict[str, Any]],
    *,
    school: Any | None = None,
    import_kind: str = "",
) -> dict[str, Any]:
    """
    Turn validation rows into Execution Path + Action Steps without hallucinating row data.
    """
    fixes: list[dict[str, Any]] = []
    for idx, row in enumerate(errors[:50]):
        if not isinstance(row, dict):
            continue
        message = str(row.get("message") or row.get("error") or "").strip()
        field = str(row.get("field") or row.get("column") or "").strip()
        row_num = row.get("row") or row.get("line") or idx + 1
        execution_path = "**Data > Imports > Error review**"
        action_steps = [
            f"Locate row {row_num} in the import error panel.",
            "Correct the value shown in the error detail.",
            "Click Re-validate row or Re-upload the corrected file.",
        ]
        for pattern, path, hint in _IMPORT_ERROR_HINTS:
            if pattern.search(message):
                execution_path = path
                action_steps = [hint] + action_steps[1:]
                break
        fixes.append(
            {
                "row": row_num,
                "field": field,
                "message": message[:500],
                "execution_path": execution_path,
                "action_steps": action_steps,
            }
        )

    topology = search_topology(user, "import upload bulk", school=school, limit=3)
    nav_url = None
    for hit in topology:
        if hit.get("url") and not hit.get("locked"):
            nav_url = hit.get("url")
            break

    summary = (
        f"Reviewed {len(fixes)} validation issue(s)"
        + (f" for {import_kind}." if import_kind else ".")
    )
    return {
        "success": True,
        "guided": {
            "summary": summary,
            "actions": [
                {
                    "title": f"Row {f['row']}",
                    "detail": f"{f.get('field', '')}: {f['message'][:200]} → {f['execution_path']}",
                }
                for f in fixes[:12]
            ],
            "cautions": [
                "Do not paste student PII into AI chat; use row numbers only.",
            ],
            "references": [nav_url] if nav_url else [],
        },
        "fixes": fixes,
        "meta": {"import_kind": import_kind, "resolver": "deterministic"},
    }


def guardrail_report_recommend(
    user: Any,
    query: str,
    *,
    school: Any | None = None,
) -> dict[str, Any]:
    """Report recommendations with permission gate + JSON schema enforcement."""
    allowed, missing = True, None
    try:
        if not user.has_feature_permission("reports.view"):
            allowed, missing = False, "feature:reports.view"
    except Exception:
        pass

    if not allowed:
        return {
            "success": True,
            "recommendations": [],
            "permission_denied": True,
            "guided": {
                "summary": (
                    "As your current role, you do not possess report-library clearance. "
                    "Contact a Campus Business Manager to run ad-hoc reports."
                ),
                "actions": [],
                "cautions": [missing or "reports.view"],
                "references": [],
            },
            "meta": {"guardrail": "permission"},
        }

    from apps.siteconfig.prompt_registry import get_prompt_template
    from services.ai_gateway import TaskType, invoke
    from services.ai_helpers import normalize_gateway_metadata

    prompt = (
        get_prompt_template("report_library", {"query": query}) or ""
    ).strip() or (
        f"Recommend reports from the library. User need: {query}\n\n"
        'Respond with JSON only: {"recommendations": [{"name", "description", "fit"}]}.'
    )
    school_id = str(getattr(school, "id", "") or "") or None
    md = normalize_gateway_metadata(
        {
            "school": school,
            "school_id": school_id,
            "tenant_id": school_id,
            "user_id": str(getattr(user, "pk", "") or getattr(user, "id", "") or ""),
            "role": getattr(user, "role", None),
        }
    )
    result, meta = invoke(
        TaskType.SETUP_RECOMMEND,
        prompt,
        user_query=query,
        metadata=md,
        response_schema="report_recommend",
    )
    recs = result.get("recommendations", []) if isinstance(result, dict) else []
    if not isinstance(recs, list):
        recs = []
    safe = []
    for item in recs[:8]:
        if not isinstance(item, dict):
            continue
        safe.append(
            {
                "name": str(item.get("name") or "")[:120],
                "description": str(item.get("description") or "")[:400],
                "fit": str(item.get("fit") or "")[:200],
            }
        )
    return {
        "success": True,
        "recommendations": safe,
        "meta": meta,
        "guided": {
            "summary": f"Found {len(safe)} report(s) that may fit your question.",
            "actions": [
                {"title": r["name"], "detail": r.get("description", "")} for r in safe
            ],
            "cautions": ["Export paths still require your role's export permission."],
            "references": [],
        },
    }


def plan_guided_tour(
    user: Any,
    goal: str,
    *,
    school: Any | None = None,
    active_url: str = "",
) -> dict[str, Any]:
    """Produce an in-app tour plan from topology + setup-assistant grounding."""
    goal_q = (goal or "").strip()
    hits = search_topology(user, goal_q, school=school, limit=5)
    steps: list[dict[str, str]] = []
    for hit in hits:
        if hit.get("locked") or not hit.get("url"):
            continue
        steps.append(
            {
                "title": str(hit.get("label") or "Open surface"),
                "execution_path": str(hit.get("path_label") or ""),
                "url": str(hit.get("url") or ""),
                "action": "Navigate and complete the on-screen checklist for this area.",
            }
        )

    if not steps:
        steps.append(
            {
                "title": "AI Center — setup assistant",
                "execution_path": "**Platform > AI Center > Setup assistant**",
                "url": "",
                "action": "Ask the setup assistant to break the goal into school-specific steps.",
            }
        )

    from services.ai.gateway import process_platform_query

    engine = process_platform_query(
        user,
        active_url,
        f"Plan a short guided tour for: {goal_q}. List 3-5 numbered steps only.",
        school=school,
        actor_roles=_actor_roles(user),
        actor_is_staff=bool(getattr(user, "is_staff", False)),
        actor_is_superuser=bool(getattr(user, "is_superuser", False)),
    )
    narrative = str(engine.get("response") or "")[:1200]
    ok, _ = validate_response_structure(narrative)
    return {
        "success": True,
        "tour_id": re.sub(r"[^a-z0-9]+", "-", goal_q.lower())[:48].strip("-") or "tour",
        "goal": goal_q,
        "steps": steps,
        "narrative": narrative if ok or engine.get("escalation_required") else narrative,
        "escalation_required": bool(engine.get("escalation_required")),
        "meta": engine.get("meta") or {},
    }
