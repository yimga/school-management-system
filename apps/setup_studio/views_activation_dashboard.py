"""Operator wizard activation dashboard + search API + bulk-promote preset (v4.00.8 #2–10).

Three views in one module:

* ``WizardActivationDashboardView`` — staff-only operator surface showing
  per-wizard completion stats + widget heatmap + drop-off points
* ``WizardSearchAPIView`` — JSON search over the wizard registry
* ``BulkPromoteCockpitPresetAPIView`` — POST endpoint that promotes
  a curated set of cockpit ids to the role/page default layout in one call
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View

logger = logging.getLogger(__name__)


# Pre-curated cockpit promote presets keyed by use-case slug.
_BULK_PROMOTE_PRESETS: dict[str, list[str]] = {
    "manager_focused":    ["cockpit-manager_200x-audit_feed", "cockpit-manager_200x-slo_clocks", "cockpit-manager_200x-tenant_heatmap"],
    "finance_focused":    ["cockpit-front_office_200x-revenue_cohort", "cockpit-front_office_200x-revenue_waterfall", "cockpit-front_office_200x-churn_scorecard"],
    "tenant_admin_quick": ["cockpit-tenant-community_band", "cockpit-tenant-newsletter_band", "cockpit-tenant_v3-today_snapshot"],
    "parent_today":       ["cockpit-tenant_v3-today_snapshot", "cockpit-tenant_v3-upcoming_events_strip", "cockpit-tenant_v3-quick_actions_grid"],
    "teacher_class_view": ["cockpit-tenant_v3-gradebook_trend", "cockpit-tenant_v3-attendance_heatmap", "cockpit-tenant_v3-lesson_of_day"],
    "student_pulse":      ["cockpit-tenant_v3-year_progress", "cockpit-tenant_v3-ai_study_buddy", "cockpit-tenant_v3-achievements_card"],
}


@method_decorator(staff_member_required, name="dispatch")
class WizardActivationDashboardView(LoginRequiredMixin, View):
    """Operator-only — per-wizard activation metrics + widget heatmap.

    # rbac-allow: super-staff-wizard-activation-dashboard
    """

    template = "setup_studio/super_activation_dashboard.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        # Wizard stats
        wizard_stats: list[dict[str, Any]] = []
        try:
            from apps.setup_studio.models import SetupProgress
            from apps.setup_studio.wizard_analytics import aggregate_wizard_stats

            # tenant-isolation-allow: super-staff-operator-dashboard-cross-tenant-aggregate
            stats = aggregate_wizard_stats(SetupProgress.objects.all().iterator())  # noqa: BLE001
            wizard_stats = sorted(
                ({
                    "wizard_key": s.wizard_key,
                    "started": s.started,
                    "completed": s.completed,
                    "abandoned": s.abandoned,
                    "completion_rate": s.completion_rate,
                    "biggest_dropoff_step": s.biggest_dropoff_step or "",
                    "median_completion_seconds": s.median_completion_seconds,
                    "p95_completion_seconds": s.p95_completion_seconds,
                } for s in stats.values()),
                key=lambda d: -d["started"],
            )
        except Exception as exc:  # noqa: BLE001 — analytics is best-effort
            logger.debug("activation dashboard: wizard stats unavailable: %s", exc)

        # Widget heatmap
        widget_heatmap: list[dict[str, Any]] = []
        try:
            from apps.runtime_blueprints.models import DashboardLayout
            from apps.setup_studio.wizard_analytics import aggregate_widget_heatmap

            heatmap = aggregate_widget_heatmap(DashboardLayout.objects.exclude(layout__isnull=True).iterator())
            widget_heatmap = sorted(
                ({"widget_id": wid, **counts} for wid, counts in heatmap.items()),
                key=lambda d: -(d.get("placed_count", 0) + d.get("promoted_count", 0)),
            )[:50]
        except Exception as exc:  # noqa: BLE001
            logger.debug("activation dashboard: widget heatmap unavailable: %s", exc)

        # Bulk-promote presets (catalog)
        presets = [
            {"slug": slug, "label": slug.replace("_", " ").title(), "widget_count": len(ids)}
            for slug, ids in _BULK_PROMOTE_PRESETS.items()
        ]

        return render(request, self.template, {
            "wizard_stats": wizard_stats,
            "widget_heatmap": widget_heatmap,
            "presets": presets,
        })


class WizardSearchAPIView(LoginRequiredMixin, View):
    """JSON search over the wizard registry. # rbac-allow: authenticated-user-wizard-search"""

    def get(self, request: HttpRequest) -> JsonResponse:
        query = request.GET.get("q", "").strip()
        audience_filter = request.GET.get("audience", "").strip() or None
        if audience_filter and audience_filter not in {"operator", "tenant_admin", "teacher", "parent", "student", "staff"}:
            audience_filter = None
        # RBAC: only an operator (is_staff) may enumerate across audiences. A
        # non-operator is locked to their OWN resolved audience so a tenant user
        # cannot pass ?audience=operator to enumerate operator-only wizard
        # metadata (super_create_school, jit_operator_*, etc.). Fail closed: an
        # unresolved audience returns nothing rather than the full catalog.
        if not getattr(getattr(request, "user", None), "is_staff", False):
            try:
                from apps.setup_studio.wizard_views import _user_audience

                own_audience = _user_audience(request)
            except Exception:  # noqa: BLE001 — audience resolution never opens the gate
                own_audience = None
            if not own_audience:
                return JsonResponse({"results": [], "count": 0})
            audience_filter = own_audience
        try:
            from apps.setup_studio import wizard_engine
            from apps.setup_studio.wizard_analytics import build_wizard_search_index, search_wizards

            index = build_wizard_search_index(wizard_engine.WIZARD_REGISTRY.values())
            if query:
                results = search_wizards(index, query=query, audience=audience_filter)
            else:
                # No query: return audience-scoped catalog
                results = [e for e in index if audience_filter is None or audience_filter in e["audience"]]
            return JsonResponse({"results": results, "count": len(results)})
        except Exception as exc:  # noqa: BLE001
            logger.warning("wizard search failed: %s", exc)
            return JsonResponse({"results": [], "count": 0, "error": "search_unavailable"}, status=200)


@method_decorator(staff_member_required, name="dispatch")
class BulkPromoteCockpitPresetAPIView(LoginRequiredMixin, View):
    """POST { preset: <slug>, role: <ROLE>, page: <page> } applies a preset to
    the role/page default layout.

    # rbac-allow: super-staff-bulk-cockpit-preset-apply
    """

    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            body = json.loads(request.body or "{}")
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "invalid_json"}, status=400)
        preset = (body.get("preset") or "").strip()
        role = (body.get("role") or "").strip().upper()
        page = (body.get("page") or "").strip().lower()
        ids = _BULK_PROMOTE_PRESETS.get(preset)
        if not ids:
            return JsonResponse({"error": "unknown_preset"}, status=400)
        if not role or not page:
            return JsonResponse({"error": "missing_role_or_page"}, status=400)
        try:
            from apps.siteconfig.views_dashboard_defaults_admin import (
                _resolve_default_layout,
                _read_requested_and_promoted,
                _write_requested_and_promoted,
            )

            layout = _resolve_default_layout(role, page)
            requested_ids, existing_promoted = _read_requested_and_promoted(layout)
            new_promoted = sorted(set(existing_promoted) | set(ids))
            _write_requested_and_promoted(layout, requested_ids=requested_ids, promoted_ids=new_promoted)
            logger.info(
                "bulk_promote_preset: actor=%s preset=%s role=%s page=%s added=%d total=%d",
                getattr(request.user, "pk", None), preset, role, page,
                len(set(ids) - set(existing_promoted)), len(new_promoted),
            )
            return JsonResponse({
                "status": "ok",
                "preset": preset,
                "role": role,
                "page": page,
                "promoted_total": len(new_promoted),
                "added": sorted(set(ids) - set(existing_promoted)),
            })
        except Exception as exc:  # noqa: BLE001
            logger.exception("bulk_promote_preset failed: %s", exc)
            return JsonResponse({"error": "apply_failed"}, status=500)
