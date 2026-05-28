"""Bridge between cockpit-section defaults and the DashboardWidget registry.

Background
----------
Two parallel widget systems exist on the platform:

* ``apps.siteconfig.dashboard_registry`` + ``DashboardWidget`` — the
  user-customizable dashboard catalog (drag/drop, hide/show, resize).
* ``apps.siteconfig.cockpit_*`` modules — the operator-curated landing
  pages with 10+ "200x" cockpit sections per surface (manager / front
  office / tenant / shipper / pulse / activity ticker / etc.).

Before v3.99.23 these did not talk to each other: cockpit sections only
appeared on the landing pages where their partial was hardcoded, and the
dashboard add-widget palette had no awareness of them. This bridge gives
the dashboard registry a read-only view of cockpit sections as
"widget-like" catalog entries so:

1. The widget gallery (discoverable add) can offer cockpit sections as
   pinned-to-dashboard items.
2. The available-widgets API can return a unified list.
3. Future work can promote a chosen dashboard widget to be a cockpit
   slot on a landing page.

The bridge does NOT mutate cockpit storage; cockpit sections continue to
be authored via ``SiteSettings.cockpit_payload``. The dashboard side
just reads the catalog. Cockpit-payload-driven enable/disable is
respected: a section reported as ``enabled=False`` in defaults is
flagged ``hidden_by_default=True`` so the gallery can show it as
"available but currently inactive".

Tenancy
-------
Cockpit catalog is platform-wide static metadata (function names + scope
labels). No tenant-specific data is leaked. Per-tenant enable/disable is
resolved at render time via the existing cockpit context processor.

Marketplace widget boundary
---------------------------
Marketplace-installed widgets (``apps/marketplace/services::get_installed_widgets``)
are deliberately NOT merged into this catalog. They live in the
``AppInstallation.widget_config`` JSON per tenant and render via the
marketplace's own template path. The intentional isolation:

* Prevents id-namespace collisions with built-in widgets and cockpit ids
* Keeps the marketplace sandbox auditable separately from the cockpit catalog
* Lets the marketplace evolve its own widget contract without touching cockpit

If the dashboard add-widget gallery should also surface marketplace
widgets in a future wave, the join point is
``apps/siteconfig/dashboard_registry.py::get_tenant_dashboard_registry``
which already returns ``installed_app_widgets`` alongside ``cockpit_widgets``
— surfacing them in the gallery is a JS-side merge, not a catalog change.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# Static catalog: (cockpit_module, section_id, display_name, host_scope, default_enabled, widget_type)
# host_scope values: "manager" (control-plane landing) / "tenant" (portal landing) / "front_office" / "any".
# widget_type values: "metric", "chart", "list", "feed", "map", "table", "summary", "media".
_COCKPIT_CATALOG: tuple[tuple[str, str, str, str, bool, str], ...] = (
    # Manager 200x (cockpit_manager_200x.py)
    ("manager_200x", "ai_copilot",            "AI Copilot Rail",          "manager", True,  "feed"),
    ("manager_200x", "world_map",             "Live World Map",            "manager", False, "map"),
    ("manager_200x", "forecast",              "Forecast Lane",             "manager", False, "chart"),
    ("manager_200x", "operator_notebook",     "Operator Notebook",         "manager", False, "list"),
    ("manager_200x", "tenant_heatmap",        "Tenant Heatmap",            "manager", False, "chart"),
    ("manager_200x", "revenue_waterfall",     "Revenue Waterfall",         "manager", False, "chart"),
    ("manager_200x", "audit_feed",            "Audit Feed",                "manager", False, "feed"),
    ("manager_200x", "trust_nutrition",       "Trust Nutrition Label",     "manager", False, "summary"),
    ("manager_200x", "slo_clocks",            "SLO Clocks",                "manager", False, "metric"),
    ("manager_200x", "operator_presence",     "Operator Presence",         "manager", False, "list"),
    # Front-office 200x (cockpit_front_office_200x.py)
    ("front_office_200x", "revenue_cohort",   "Revenue Cohort",            "front_office", False, "chart"),
    ("front_office_200x", "nps_ticker",       "NPS Ticker",                "front_office", False, "metric"),
    ("front_office_200x", "support_burndown", "Support Burndown",          "front_office", False, "chart"),
    ("front_office_200x", "deploy_pipeline",  "Deploy Pipeline",           "front_office", False, "list"),
    ("front_office_200x", "churn_scorecard",  "Churn Scorecard",           "front_office", False, "summary"),
    ("front_office_200x", "ai_fixes_feed",    "AI Fixes Feed",             "front_office", False, "feed"),
    ("front_office_200x", "capacity_planning","Capacity Planning",         "front_office", False, "chart"),
    ("front_office_200x", "regional_clocks",  "Regional Clocks",           "front_office", False, "metric"),
    ("front_office_200x", "onboarding_pipeline","Onboarding Pipeline",     "front_office", False, "list"),
    ("front_office_200x", "audit_wordcloud",  "Audit Word Cloud",          "front_office", False, "media"),
    # Tenant cockpit (cockpit_context.py default helpers — exposed on portal landings)
    ("tenant",  "community_band",             "Community Band",            "tenant", False, "summary"),
    ("tenant",  "newsletter_band",            "Newsletter Band",           "tenant", False, "media"),
    ("tenant",  "sibling_compare",            "Sibling Compare",           "tenant", False, "table"),
    ("tenant",  "signup_form",                "Signup Form",               "tenant", False, "summary"),
    ("tenant",  "tenant_footer",              "Tenant Footer",             "tenant", False, "summary"),
    # Activity ticker (cockpit_activity_ticker_realdata.py — host-aware split)
    ("activity_ticker", "manager_ticker",     "Activity Ticker (Manager)", "manager", True,  "feed"),
    ("activity_ticker", "tenant_ticker",      "Activity Ticker (Tenant)",  "tenant",  True,  "feed"),
    # Calendar + weather (cockpit_calendar_weather_runtime.py)
    ("calendar_weather", "live_weather",      "Calendar + Live Weather",   "any",     False, "summary"),
    # v4.00.5: 21 additional cockpit sections previously orphaned from the catalog
    # (partials existed but were landing-only — gallery couldn't offer them).
    ("tenant_v3",  "achievements_card",       "Achievements Card",         "tenant", False, "summary"),
    ("tenant_v3",  "activity_timeline",       "Activity Timeline",         "tenant", False, "feed"),
    ("tenant_v3",  "ai_study_buddy",          "AI Study Buddy",            "tenant", False, "feed"),
    ("tenant_v3",  "attendance_heatmap",      "Attendance Heatmap",        "tenant", False, "chart"),
    ("tenant_v3",  "financial_timeline",      "Financial Timeline",        "tenant", False, "list"),
    ("tenant_v3",  "gradebook_trend",         "Gradebook Trend",           "tenant", False, "chart"),
    ("tenant_v3",  "lesson_of_day",           "Lesson of the Day",         "tenant", False, "summary"),
    ("tenant_v3",  "life_event_timeline",     "Life Event Timeline",       "tenant", False, "feed"),
    ("tenant_v3",  "parent_teacher_thread",   "Parent–Teacher Thread",     "tenant", False, "feed"),
    ("tenant_v3",  "quick_actions_grid",      "Quick Actions Grid",        "tenant", False, "list"),
    ("tenant_v3",  "teacher_spotlight_card",  "Teacher Spotlight",         "tenant", False, "summary"),
    ("tenant_v3",  "today_snapshot",          "Today Snapshot",            "tenant", False, "summary"),
    ("tenant_v3",  "tp_pulse_drill_sheet",    "Tenant Pulse Drill",        "tenant", False, "list"),
    ("tenant_v3",  "upcoming_events_strip",   "Upcoming Events Strip",     "tenant", False, "list"),
    ("tenant_v3",  "workspace_context_tenant","Workspace Context (Tenant)","tenant", False, "summary"),
    ("tenant_v3",  "year_progress",           "Year Progress",             "tenant", False, "metric"),
    ("manager_extended", "platform_pulse",    "Platform Pulse",            "manager", False, "metric"),
    ("manager_extended", "pulse_drill_sheet", "Pulse Drill Sheet",         "manager", False, "list"),
    ("manager_extended", "realtime_presence", "Realtime Presence",         "manager", False, "list"),
    ("manager_extended", "trust_pillars_alerts","Trust Pillars Alerts",    "manager", False, "feed"),
    ("manager_extended", "workspace_context", "Workspace Context",         "manager", False, "summary"),
    # v4.00.12: Admissions queue depth tile (closes v3.97.0 deferral)
    ("manager_extended", "admissions_queue",  "Admissions Queue Depth",    "manager", False, "metric"),
    ("tenant_v3",        "admissions_queue",  "Admissions Queue Depth",    "tenant",  False, "metric"),
    # v4.00.13: Enrollment forecast tile (closes v3.97.0 forecast surface)
    ("manager_extended", "enrollment_forecast","Enrollment Forecast",      "manager", False, "metric"),
    ("tenant_v3",        "enrollment_forecast","Enrollment Forecast",      "tenant",  False, "metric"),
)


_PAGE_TO_HOST_SCOPE = {
    "backend":          ("manager", "manager_extended", "front_office", "any"),
    "backend-dashboard":("manager", "manager_extended", "front_office", "any"),
    "backend_console":  ("manager", "manager_extended", "front_office", "any"),
    "admin":            ("manager", "manager_extended", "any"),
    "finance":          ("front_office", "tenant_v3", "any"),
    "analytics":        ("front_office", "tenant_v3", "any"),
    "parent":           ("tenant", "tenant_v3", "any"),
    "teacher":          ("tenant", "tenant_v3", "any"),
    "student":          ("tenant", "tenant_v3", "any"),
    "entity-console":   ("manager", "manager_extended", "any"),
}


def _make_cockpit_widget_entry(
    module: str,
    section_id: str,
    display_name: str,
    host_scope: str,
    default_enabled: bool,
    widget_type: str,
) -> dict[str, Any]:
    """Shape a catalog row to match the DashboardWidget JSON surface.

    The returned dict is intentionally a superset of ``DashboardWidget``
    fields so consumers can render uniform UI; cockpit-specific fields
    sit under ``cockpit_*`` keys.
    """
    widget_id = f"cockpit-{module}-{section_id}"
    return {
        "id": widget_id,
        "name": display_name,
        "description": f"Cockpit section from {module}.{section_id}. Configure on the landing page or via SiteSettings.cockpit_payload.",
        "widget_type": widget_type,
        "page": None,  # cockpit sections are page-agnostic; gallery filters by host_scope instead
        "required_role": "ANY",
        "allowed_roles": [],
        "allowed_sizes": ["md", "lg"],
        "default_size": "lg",
        "allowed_variants": ["default"],
        "default_variant": "default",
        "source": "cockpit",
        "cockpit_module": module,
        "cockpit_section_id": section_id,
        "cockpit_host_scope": host_scope,
        "cockpit_default_enabled": default_enabled,
        "hidden_by_default": not default_enabled,
    }


def list_cockpit_widget_catalog(
    *,
    page: str | None = None,
    host_scope: str | None = None,
) -> list[dict[str, Any]]:
    """Return the static cockpit widget catalog, optionally filtered.

    ``page`` is the dashboard page slug (``backend`` / ``parent`` /
    ``teacher`` / etc.). If provided, only cockpit sections whose
    ``host_scope`` is admissible for that page are returned.

    ``host_scope`` allows direct filtering when the caller already knows
    the scope (e.g. shell-level integration).
    """
    if page is not None:
        admissible = set(_PAGE_TO_HOST_SCOPE.get(page.lower(), ("any",)))
    elif host_scope is not None:
        admissible = {host_scope}
    else:
        admissible = None

    out: list[dict[str, Any]] = []
    for row in _COCKPIT_CATALOG:
        module, section_id, name, scope, default_enabled, widget_type = row
        if admissible is not None and scope not in admissible and "any" not in admissible:
            continue
        out.append(_make_cockpit_widget_entry(module, section_id, name, scope, default_enabled, widget_type))
    return out


def merge_dashboard_and_cockpit_widgets(
    dashboard_widgets: Iterable[dict[str, Any]],
    *,
    page: str | None = None,
) -> list[dict[str, Any]]:
    """Combine native ``DashboardWidget`` rows with cockpit catalog rows.

    Native widgets keep ``source='builtin'``; cockpit additions carry
    ``source='cockpit'`` so the gallery UI can group them visually.
    Native widgets win on id collisions (defensive — should not happen
    given ``cockpit-`` prefix).
    """
    seen_ids: set[str] = set()
    merged: list[dict[str, Any]] = []
    for entry in dashboard_widgets:
        if not isinstance(entry, dict):
            continue
        wid = entry.get("id")
        if wid and wid not in seen_ids:
            seen_ids.add(wid)
            merged.append(entry)
    for entry in list_cockpit_widget_catalog(page=page):
        if entry["id"] not in seen_ids:
            seen_ids.add(entry["id"])
            merged.append(entry)
    return merged


def cockpit_section_to_widget_id(module: str, section_id: str) -> str:
    """Public helper: deterministic widget id for a (module, section_id) pair."""
    return f"cockpit-{module}-{section_id}"


# Mapping: cockpit section_id → partial template path under templates/partials/cockpit/
# Convention: section_id mostly matches the filename; explicit map handles renames + ambiguity.
_SECTION_TO_PARTIAL: dict[str, str] = {
    "ai_copilot":          "partials/cockpit/_ai_copilot_rail.html",
    "world_map":           "partials/cockpit/_live_world_map.html",
    "forecast":            "partials/cockpit/_forecast_lane.html",
    "operator_notebook":   "partials/cockpit/_operator_notebook.html",
    "tenant_heatmap":      "partials/cockpit/_tenant_heatmap.html",
    "revenue_waterfall":   "partials/cockpit/_revenue_waterfall.html",
    "audit_feed":          "partials/cockpit/_audit_feed.html",
    "trust_nutrition":     "partials/cockpit/_trust_nutrition.html",
    "slo_clocks":          "partials/cockpit/_slo_clocks.html",
    "operator_presence":   "partials/cockpit/_operator_presence.html",
    "revenue_cohort":      "partials/cockpit/_revenue_cohort.html",
    "nps_ticker":          "partials/cockpit/_nps_ticker.html",
    "support_burndown":    "partials/cockpit/_support_burndown.html",
    "deploy_pipeline":     "partials/cockpit/_deploy_pipeline.html",
    "churn_scorecard":     "partials/cockpit/_churn_scorecard.html",
    "ai_fixes_feed":       "partials/cockpit/_ai_fixes_feed.html",
    "capacity_planning":   "partials/cockpit/_capacity_planning.html",
    "regional_clocks":     "partials/cockpit/_regional_clocks.html",
    "onboarding_pipeline": "partials/cockpit/_onboarding_pipeline.html",
    "audit_wordcloud":     "partials/cockpit/_audit_wordcloud.html",
    "community_band":      "partials/cockpit/_community_band.html",
    "newsletter_band":     "partials/cockpit/_newsletter_band.html",
    "sibling_compare":     "partials/cockpit/_sibling_compare.html",
    "signup_form":         "partials/cockpit/_signup_form.html",
    "tenant_footer":       "partials/cockpit/_tenant_footer.html",
    "manager_ticker":      "partials/cockpit/_activity_ticker.html",
    "tenant_ticker":       "partials/cockpit/_activity_ticker.html",
    "live_weather":        "partials/cockpit/_calendar_weather.html",
    # v4.00.5: 21 sections previously orphaned from the catalog
    "achievements_card":       "partials/cockpit/_achievements_card.html",
    "activity_timeline":       "partials/cockpit/_activity_timeline.html",
    "ai_study_buddy":          "partials/cockpit/_ai_study_buddy.html",
    "attendance_heatmap":      "partials/cockpit/_attendance_heatmap.html",
    "financial_timeline":      "partials/cockpit/_financial_timeline.html",
    "gradebook_trend":         "partials/cockpit/_gradebook_trend.html",
    "lesson_of_day":           "partials/cockpit/_lesson_of_day.html",
    "life_event_timeline":     "partials/cockpit/_life_event_timeline.html",
    "parent_teacher_thread":   "partials/cockpit/_parent_teacher_thread.html",
    "quick_actions_grid":      "partials/cockpit/_quick_actions_grid.html",
    "teacher_spotlight_card":  "partials/cockpit/_teacher_spotlight_card.html",
    "today_snapshot":          "partials/cockpit/_today_snapshot.html",
    "tp_pulse_drill_sheet":    "partials/cockpit/_tp_pulse_drill_sheet.html",
    "upcoming_events_strip":   "partials/cockpit/_upcoming_events_strip.html",
    "workspace_context_tenant":"partials/cockpit/_workspace_context_tenant.html",
    "year_progress":           "partials/cockpit/_year_progress.html",
    "platform_pulse":          "partials/cockpit/_platform_pulse.html",
    "pulse_drill_sheet":       "partials/cockpit/_pulse_drill_sheet.html",
    "realtime_presence":       "partials/cockpit/_realtime_presence.html",
    "trust_pillars_alerts":    "partials/cockpit/_trust_pillars_alerts.html",
    "workspace_context":       "partials/cockpit/_workspace_context.html",
    # v4.00.12: Admissions queue depth tile (shared partial across host_scope)
    "admissions_queue":        "partials/cockpit/_admissions_queue.html",
    # v4.00.13: Enrollment forecast tile
    "enrollment_forecast":     "partials/cockpit/_enrollment_forecast.html",
}


def widget_id_to_partial_path(widget_id: str) -> str | None:
    """Given a cockpit widget id (``cockpit-<module>-<section_id>``), return the partial path or None.

    Used by the dashboard renderer to resolve promoted cockpit widgets to a
    partial. Returns None for non-cockpit ids or unknown sections. Also
    returns None when the mapped partial does not exist on the template
    loader's path — defends the dashboard render from a TemplateDoesNotExist
    surfaced by a stale catalog entry.
    """
    if not widget_id.startswith("cockpit-"):
        return None
    parts = widget_id.split("-", 2)
    if len(parts) < 3:
        return None
    section_id = parts[2]
    partial = _SECTION_TO_PARTIAL.get(section_id)
    if not partial:
        return None
    try:
        from django.template.loader import get_template

        get_template(partial)
    except Exception:  # noqa: BLE001 — TemplateDoesNotExist or any loader error treats as unavailable
        return None
    return partial


def resolve_promoted_cockpit_partials(promoted_ids: list[str] | None) -> list[dict[str, Any]]:
    """Map a list of promoted cockpit widget ids to ``{id, name, partial_path}`` rows.

    Unknown ids are dropped silently (defense — the layout settings could
    drift from the catalog over time).
    """
    if not promoted_ids:
        return []
    name_by_id = {row[1]: row[2] for row in (
        # (module, section_id, name, host_scope, default_enabled, widget_type)
        (m, s, n, h, e, t) for (m, s, n, h, e, t) in _COCKPIT_CATALOG
    )}
    out = []
    for wid in promoted_ids:
        partial = widget_id_to_partial_path(wid)
        if not partial:
            continue
        parts = wid.split("-", 2)
        section_id = parts[2] if len(parts) >= 3 else ""
        out.append({
            "id": wid,
            "name": name_by_id.get(section_id) or section_id,
            "partial_path": partial,
        })
    return out
