"""Owner Console — Workflows (read-only registry over the existing engine).

Wave 7.1. The school already has an automation engine — school-authored no-code
automations (``siteconfig.SchoolAutomationWorkflow``), activated platform templates
(``siteconfig.TenantWorkflow``) and visual graph workflows (``automation.Workflow``).
What it lacked was one owner-facing place to *see* them: what's running, on what
trigger, when it last ran. This registry surfaces the school's own definitions and
deep-links ("Open builder") into the existing designer/builder surfaces.

It is read-only, owner-gated, tenant-skinned and fail-soft: it never authors or runs
a workflow, and every data read degrades to a safe default so the page never 500s.
The last-run lookups are deliberately isolated from the base list, so a missing log
row (or a renamed relation) blanks a timestamp — never the whole registry.
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.shortcuts import render
from django.utils.translation import gettext as _

from apps.accounts.views_owner_console import _owner_only, _safe
from apps.schools.mixins import require_school

logger = logging.getLogger(__name__)

# Any read that touches the workflow tables can fail on a stale/partial schema; the
# registry degrades to what it could read rather than 500.
_SOFT = Exception


def _disp(obj, method: str, fallback_attr: str) -> str:
    """A display label via ``get_<field>_display()`` when present, else the raw value."""
    try:
        getter = getattr(obj, method, None)
        if callable(getter):
            val = getter()
            if val:
                return str(val)
    except _SOFT:  # noqa: BLE001 — label only, never break the row
        pass
    return str(getattr(obj, fallback_attr, "") or "")


def _last_runs(log_import: str, scope_kwargs: dict, group_field: str) -> dict:
    """`{definition_id: last_run_at}` for a run-log model, fully isolated + fail-soft."""
    try:
        module_path, cls_name = log_import.rsplit(".", 1)
        module = __import__(module_path, fromlist=[cls_name])
        model = getattr(module, cls_name)
        rows = (
            model.objects.filter(**scope_kwargs)
            .values(group_field)
            .annotate(_m=Max("created_at"))
            .values_list(group_field, "_m")
        )
        return {gid: ts for gid, ts in rows}
    except _SOFT as exc:  # noqa: BLE001 — no last-run column simply means "—"
        logger.debug("owner console workflow last-runs failed (%s): %s", log_import, exc)
        return {}


def _school_automation_rows(school) -> list[dict]:
    rows: list[dict] = []
    try:
        from apps.siteconfig.models_workflow import SchoolAutomationWorkflow

        last = _last_runs(
            "apps.siteconfig.models_workflow.SchoolWorkflowExecutionLog",
            {"workflow__school": school},
            "workflow_id",
        )
        for w in SchoolAutomationWorkflow.objects.filter(school=school).order_by("name"):
            rows.append(
                {
                    "name": w.name,
                    "trigger": _disp(w, "get_trigger_display", "trigger"),
                    "status": (getattr(w, "status", "") or "").replace("_", " ").title(),
                    "active": bool(getattr(w, "is_active", False)),
                    "last_run": last.get(w.pk),
                    "kind": "automation",
                }
            )
    except _SOFT as exc:  # noqa: BLE001
        logger.debug("owner console school automations failed: %s", exc)
    return rows


def _tenant_template_rows(school) -> list[dict]:
    rows: list[dict] = []
    try:
        from apps.siteconfig.models_workflow import TenantWorkflow

        last = _last_runs(
            "apps.siteconfig.models_workflow.WorkflowRunLog",
            {"tenant_workflow__school": school},
            "tenant_workflow_id",
        )
        qs = TenantWorkflow.objects.filter(school=school).select_related("template")
        for tw in qs.order_by("template__name"):
            template = getattr(tw, "template", None)
            rows.append(
                {
                    "name": getattr(template, "name", "") or _("Activated workflow"),
                    "trigger": _disp(template, "get_trigger_display", "trigger") if template else "",
                    "status": _("Active") if getattr(tw, "is_active", False) else _("Paused"),
                    "active": bool(getattr(tw, "is_active", False)),
                    "last_run": last.get(tw.pk),
                    "kind": "template",
                }
            )
    except _SOFT as exc:  # noqa: BLE001
        logger.debug("owner console tenant workflows failed: %s", exc)
    return rows


def _visual_rows(school) -> list[dict]:
    rows: list[dict] = []
    try:
        from apps.automation.workflow_graph_models import Workflow

        last = _last_runs(
            "apps.automation.workflow_graph_models.WorkflowRunLog",
            {"workflow__school": school},
            "workflow_id",
        )
        for w in Workflow.objects.filter(school=school).order_by("name"):
            rows.append(
                {
                    "name": w.name,
                    "trigger": _disp(w, "get_trigger_event_display", "trigger_event"),
                    "status": (getattr(w, "status", "") or "").replace("_", " ").title(),
                    "active": bool(getattr(w, "is_active", False)),
                    "last_run": last.get(w.pk),
                    "kind": "visual",
                }
            )
    except _SOFT as exc:  # noqa: BLE001
        logger.debug("owner console visual workflows failed: %s", exc)
    return rows


@login_required
@require_school
def owner_console_workflows(request):
    """Workflows — a read-only registry of the school's automations (owner-gated)."""
    ctx, denied = _owner_only(request, "workflows")
    if denied:
        return denied

    school = request.school
    groups = [
        {
            "key": "automation",
            "label": _("No-code automations"),
            "blurb": _("Rules your team built — “when this happens, do that.”"),
            "rows": _school_automation_rows(school),
            "open_url": _safe("siteconfig:school_automation_builder"),
            "open_label": _("Open builder"),
        },
        {
            "key": "template",
            "label": _("Activated templates"),
            "blurb": _("Ready-made workflows you switched on from the library."),
            "rows": _tenant_template_rows(school),
            "open_url": _safe("studio_os:automation"),
            "open_label": _("Open library"),
        },
        {
            "key": "visual",
            "label": _("Visual workflows"),
            "blurb": _("Multi-step flows drawn on the visual designer canvas."),
            "rows": _visual_rows(school),
            "open_url": _safe("automation:visual_workflow_designer"),
            "open_label": _("Open designer"),
        },
    ]
    ctx["workflow_groups"] = groups
    ctx["total_workflows"] = sum(len(g["rows"]) for g in groups)
    ctx["outcomes_url"] = _safe("automation:outcomes_console")
    return render(request, "accounts/owner_console/workflows.html", ctx)
