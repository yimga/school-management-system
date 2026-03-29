"""
Runtime inspector, runtime truth hub (platform defaults read-only), and workflow simulator
(BR-12 split from super_views).
"""

from __future__ import annotations

import csv
import hashlib
from urllib.parse import quote, urlencode

from django.http import HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from .decision_architecture import get_decision_architecture_for_page
from .models import School

_PLAYBOOK_EXECUTION_TASK_NAME = "automation.playbook.execute"
PLAYBOOK_OPERATOR_HUB_CSV_MAX_ROWS = 500
PLAYBOOK_OPERATOR_HUB_CSV_FILENAME = "playbook_execution_logs.csv"
# When ``PLAYBOOK_OPERATOR_HUB_CSV_FILENAME`` contains non-ASCII, legacy clients use this ASCII ``filename=``.
PLAYBOOK_OPERATOR_HUB_CSV_FILENAME_ASCII_FALLBACK = "playbook_execution_logs.csv"


def _playbook_operator_hub_csv_content_disposition(filename: str) -> str:
    """RFC 5987 ``filename*`` (UTF-8) plus ASCII-safe ``filename=`` for non-ASCII basenames."""
    star = quote(filename, safe="")
    try:
        filename.encode("ascii")
        primary = filename
    except UnicodeEncodeError:
        primary = PLAYBOOK_OPERATOR_HUB_CSV_FILENAME_ASCII_FALLBACK
    return f'attachment; filename="{primary}"; filename*=UTF-8\'\'{star}'


def _optional_reverse(viewname: str) -> str | None:
    try:
        return reverse(viewname)
    except NoReverseMatch:
        return None


def _collect_step_run_ids_from_logs(logs) -> set[int]:
    ids: set[int] = set()
    for log in logs:
        summary = log.execution_summary if isinstance(log.execution_summary, dict) else {}
        for step in summary.get("steps") or []:
            if not isinstance(step, dict):
                continue
            rid = step.get("run_id")
            try:
                ids.add(int(rid))
            except (TypeError, ValueError):
                continue
    return ids


def _playbook_execution_step_admin_links(
    log, present_run_pks: set[int]
) -> list[dict[str, object]]:
    """Build admin change URLs only for ``run_id`` values that still exist (stale-ID safe)."""
    summary = log.execution_summary if isinstance(log.execution_summary, dict) else {}
    steps = summary.get("steps") or []
    out: list[dict[str, object]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        rid = step.get("run_id")
        try:
            rid_int = int(rid)
        except (TypeError, ValueError):
            continue
        exists = rid_int in present_run_pks
        out.append(
            {
                "run_id": rid_int,
                "migration_type": str(step.get("migration_type") or ""),
                "step_status": str(step.get("status") or ""),
                "admin_url": (
                    reverse("admin:automation_migrationrun_change", args=[rid_int])
                    if exists
                    else None
                ),
            }
        )
    return out


def _playbook_operator_hub_csv_response(playbook_exec_qs) -> HttpResponse:
    """Filtered playbook execution logs as CSV (UTF-8 BOM for Excel; row cap constant)."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = _playbook_operator_hub_csv_content_disposition(
        PLAYBOOK_OPERATOR_HUB_CSV_FILENAME
    )
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(
        [
            "log_id",
            "started_at",
            "status",
            "execution_type",
            "school_id",
            "schema_name",
            "playbook_slug",
            "migration_run_ids",
            "step_statuses",
        ]
    )
    qs = playbook_exec_qs.order_by("-started_at")[:PLAYBOOK_OPERATOR_HUB_CSV_MAX_ROWS]
    for log in qs.iterator():
        summary = log.execution_summary if isinstance(log.execution_summary, dict) else {}
        steps = summary.get("steps") or []
        run_ids: list[str] = []
        step_statuses: list[str] = []
        for s in steps:
            if not isinstance(s, dict):
                continue
            if s.get("run_id") is not None:
                run_ids.append(str(s["run_id"]))
            st = s.get("status")
            if st is not None and str(st).strip():
                step_statuses.append(str(st))
        writer.writerow(
            [
                log.pk,
                log.started_at.isoformat() if log.started_at else "",
                log.status,
                log.execution_type,
                log.school_id or "",
                log.schema_name or "",
                summary.get("playbook_slug") or "",
                ";".join(run_ids),
                ";".join(step_statuses),
            ]
        )
    return response


def super_runtime_inspector(request):
    """Control plane: inspect tenant_runtime for a selected school (effective blueprint, packs, overrides)."""
    from apps.platform_runtime.runtime_inspector import (
        get_runtime_inspection_for_school,
    )

    school_id = (request.GET.get("school_id") or "").strip()
    school = None
    inspection = None
    schools_sample = list(
        School.objects.filter(is_active=True)
        .order_by("-last_activity", "-created_at")[:20]
        .values("id", "name", "slug")
    )
    if school_id:
        try:
            school = School.objects.get(id=school_id)
            inspection = get_runtime_inspection_for_school(school)
        except (School.DoesNotExist, ValueError):
            pass
    return render(
        request,
        "schools/super_runtime_inspector.html",
        {
            "school": school,
            "inspection": inspection,
            "schools_sample": schools_sample,
            "dashboard_url": reverse("super:dashboard"),
            "decision_architecture": get_decision_architecture_for_page(
                "runtime_inspector"
            ),
        },
    )


def super_runtime_truth_hub(request):
    """
    Read-only platform summary: RuntimeDefaults singleton + slim tenant site settings row.

    Uses ``get_platform_site_settings_record`` (platform_runtime.helpers) — same
    canonical singleton accessor as Studio rollback and backfill commands — no ad-hoc
    ORM access to the platform singleton in this view.
    """
    from apps.platform_runtime.helpers import get_platform_site_settings_record
    from apps.platform_runtime.models import PlatformOperatorTruthHubLink, RuntimeDefaults

    rt = RuntimeDefaults.get_singleton()
    payload = rt.payload if rt and isinstance(rt.payload, dict) else {}
    payload_keys = sorted(payload.keys())
    preview: list[dict[str, object]] = []
    for key in payload_keys[:48]:
        val = payload[key]
        if isinstance(val, dict):
            kind = "dict"
            extra = f"len={len(val)}"
        elif isinstance(val, list):
            kind = "list"
            extra = f"len={len(val)}"
        elif isinstance(val, bool):
            kind = "bool"
            extra = repr(val)
        elif val is None:
            kind = "null"
            extra = ""
        elif isinstance(val, (int, float)):
            kind = "number"
            extra = str(val)
        else:
            s = str(val)
            kind = "string"
            extra = s if len(s) <= 64 else s[:61] + "…"
        preview.append({"key": key, "kind": kind, "extra": extra})

    ss = get_platform_site_settings_record(create=False)
    site_settings_summary = None
    if ss is not None:
        site_settings_summary = {
            "pk": ss.pk,
            "maintenance_mode": ss.maintenance_mode,
            "updated_at": ss.updated_at,
            "has_logo": bool(getattr(ss, "logo", None)),
            "has_favicon": bool(getattr(ss, "favicon", None)),
            "theme_pack_id": getattr(ss.theme_pack, "pk", None),
            "admin_theme_pack_id": getattr(ss.admin_theme_pack, "pk", None),
        }

    from apps.automation.models import AutomationExecutionLog, MigrationPlaybook

    migration_playbook_count = MigrationPlaybook.objects.count()
    playbook_exec_qs = AutomationExecutionLog.objects.filter(
        task_name=_PLAYBOOK_EXECUTION_TASK_NAME
    )
    automation_playbook_log_count = playbook_exec_qs.count()
    latest_playbook_log = playbook_exec_qs.order_by("-started_at").first()

    from apps.runtime_blueprints.models import BlueprintPack

    bp_slugs = tuple(
        BlueprintPack.objects.order_by("slug").values_list("slug", flat=True)
    )
    joined = "\n".join(bp_slugs).encode("utf-8")
    bp_digest = hashlib.sha256(joined).hexdigest()[:16]
    blueprint_pack_catalog_fingerprint = f"n={len(bp_slugs)};sha256[:16]={bp_digest}"

    operator_truth_hub_links = list(
        PlatformOperatorTruthHubLink.objects.order_by("sort_order", "slug")
    )

    return render(
        request,
        "schools/super_runtime_truth_hub.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "runtime_defaults": rt,
            "payload_key_count": len(payload_keys),
            "payload_keys_truncated": len(payload_keys) > len(preview),
            "payload_preview": preview,
            "cache_rankings_interval_minutes": getattr(
                rt, "cache_rankings_interval_minutes", None
            )
            if rt
            else None,
            "site_settings_summary": site_settings_summary,
            "migration_playbook_count": migration_playbook_count,
            "automation_playbook_log_count": automation_playbook_log_count,
            "latest_playbook_log": latest_playbook_log,
            "admin_migration_playbook_changelist": reverse(
                "admin:automation_migrationplaybook_changelist"
            ),
            "admin_automation_execution_log_changelist": reverse(
                "admin:automation_automationexecutionlog_changelist"
            ),
            "workflow_simulator_url": reverse("super:workflow_simulator"),
            "studio_automation_url": _optional_reverse("studio_os:automation"),
            "outcomes_console_url": _optional_reverse("automation:outcomes_console"),
            "playbook_execution_task_name": _PLAYBOOK_EXECUTION_TASK_NAME,
            "blueprint_pack_catalog_fingerprint": blueprint_pack_catalog_fingerprint,
            "decision_architecture": get_decision_architecture_for_page(
                "runtime_truth_hub"
            ),
            "operator_truth_hub_links": operator_truth_hub_links,
        },
    )


def super_workflow_simulator(request):
    """Control plane: simulate workflow/pack resolution for a selected school and role."""
    from apps.platform_runtime.models import PlatformOperatorWorkflowSimulatorLink

    school_id = (request.GET.get("school_id") or "").strip()
    role = (request.GET.get("role") or "ADMIN").strip().upper()
    school = None
    workflow_summary = None
    if school_id:
        try:
            school = School.objects.get(id=school_id)
            from apps.platform_runtime.runtime_resolver import (
                build_tenant_runtime_for_tenant,
            )

            rt = build_tenant_runtime_for_tenant(
                school, user=getattr(request, "user", None)
            )
            if rt and hasattr(rt, "workflow_for"):
                wf = rt.workflow_for(role)
                workflow_summary = {
                    "role": role,
                    "workflow_id": getattr(wf, "id", None),
                    "workflow_slug": getattr(wf, "slug", None),
                }
            elif rt and hasattr(rt, "policy"):
                workflow_summary = {
                    "role": role,
                    "workflow_id": None,
                    "workflow_slug": None,
                    "note": "workflow_for not available",
                }
        except (School.DoesNotExist, ValueError):
            pass
    return render(
        request,
        "schools/super_workflow_simulator.html",
        {
            "school": school,
            "workflow_summary": workflow_summary,
            "dashboard_url": reverse("super:dashboard"),
            "operator_workflow_simulator_links": PlatformOperatorWorkflowSimulatorLink.objects.order_by(
                "sort_order", "slug"
            ),
        },
    )


def super_playbook_operator_hub(request):
    """
    Control plane: migration playbooks, recent ``execute_playbook`` audit rows, and
    curated deep links (``PlatformOperatorPlaybookLink`` typed table + static anchors).
    """
    from apps.automation.models import AutomationExecutionLog, MigrationPlaybook
    from apps.platform_runtime.models import PlatformOperatorPlaybookLink

    status_raw = (request.GET.get("status") or "").strip().upper()
    exec_type_raw = (request.GET.get("execution_type") or "").strip().upper()
    valid_status = {c.value for c in AutomationExecutionLog.Status}
    valid_exec = {c.value for c in AutomationExecutionLog.ExecutionType}

    known_playbook_slugs = frozenset(
        MigrationPlaybook.objects.values_list("slug", flat=True)
    )
    playbook_slug_raw = (request.GET.get("playbook_slug") or "").strip()
    playbook_log_playbook_slug_filter = ""
    if playbook_slug_raw and playbook_slug_raw in known_playbook_slugs:
        playbook_log_playbook_slug_filter = playbook_slug_raw

    playbook_exec_qs = AutomationExecutionLog.objects.filter(
        task_name=_PLAYBOOK_EXECUTION_TASK_NAME
    )
    if status_raw in valid_status:
        playbook_exec_qs = playbook_exec_qs.filter(status=status_raw)
    if exec_type_raw in valid_exec:
        playbook_exec_qs = playbook_exec_qs.filter(execution_type=exec_type_raw)
    if playbook_log_playbook_slug_filter:
        playbook_exec_qs = playbook_exec_qs.filter(
            execution_summary__playbook_slug=playbook_log_playbook_slug_filter
        )

    export_raw = (request.GET.get("export") or "").strip().lower()
    if export_raw == "csv":
        return _playbook_operator_hub_csv_response(playbook_exec_qs)

    recent_logs = list(
        playbook_exec_qs.order_by("-started_at").select_related("school")[:25]
    )
    step_run_ids = _collect_step_run_ids_from_logs(recent_logs)
    if step_run_ids:
        from apps.automation.models import MigrationRun

        present_run_pks = set(
            MigrationRun.objects.filter(pk__in=step_run_ids).values_list("pk", flat=True)
        )
    else:
        present_run_pks = set()
    for log in recent_logs:
        sch = getattr(log, "school", None)
        log.display_school = getattr(sch, "name", None) or "—"
        log.admin_execution_log_url = reverse(
            "admin:automation_automationexecutionlog_change", args=[log.pk]
        )
        summary = log.execution_summary if isinstance(log.execution_summary, dict) else {}
        log.playbook_slug_short = str(summary.get("playbook_slug") or "")[:120]
        log.playbook_step_admin_links = _playbook_execution_step_admin_links(
            log, present_run_pks
        )

    export_params = request.GET.copy()
    export_params["export"] = "csv"
    playbook_hub_export_csv_url = (
        f"{reverse('super:playbook_operator_hub')}?{export_params.urlencode()}"
    )

    operator_links = list(
        PlatformOperatorPlaybookLink.objects.order_by("sort_order", "slug")
    )
    migration_playbooks = list(
        MigrationPlaybook.objects.order_by("slug").values("id", "slug", "name")[:40]
    )

    base_hub = reverse("super:playbook_operator_hub")
    filter_params: dict[str, str] = {}
    if status_raw in valid_status:
        filter_params["status"] = status_raw
    if exec_type_raw in valid_exec:
        filter_params["execution_type"] = exec_type_raw
    playbook_slug_filter_links = [
        {
            "slug": slug,
            "url": f"{base_hub}?{urlencode({**filter_params, 'playbook_slug': slug})}",
        }
        for slug in sorted(known_playbook_slugs)[:40]
    ]
    clear_q = urlencode(filter_params)
    playbook_hub_clear_playbook_slug_url = f"{base_hub}?{clear_q}" if clear_q else base_hub

    return render(
        request,
        "schools/super_playbook_operator_hub.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "runtime_truth_hub_url": reverse("super:runtime_truth_hub"),
            "workflow_simulator_url": reverse("super:workflow_simulator"),
            "phase_b_snapshot_diff_url": reverse("super:phase_b_snapshot_diff"),
            "admin_migration_playbook_changelist": reverse(
                "admin:automation_migrationplaybook_changelist"
            ),
            "admin_migration_run_changelist": reverse(
                "admin:automation_migrationrun_changelist"
            ),
            "admin_automation_execution_log_changelist": reverse(
                "admin:automation_automationexecutionlog_changelist"
            ),
            "admin_operator_playbook_link_changelist": reverse(
                "admin:platform_runtime_platformoperatorplaybooklink_changelist"
            ),
            "studio_automation_url": _optional_reverse("studio_os:automation"),
            "outcomes_console_url": _optional_reverse("automation:outcomes_console"),
            "playbook_execution_task_name": _PLAYBOOK_EXECUTION_TASK_NAME,
            "migration_playbook_count": MigrationPlaybook.objects.count(),
            "automation_playbook_log_count": playbook_exec_qs.count(),
            "playbook_log_status_filter": status_raw
            if status_raw in valid_status
            else "",
            "playbook_log_execution_type_filter": exec_type_raw
            if exec_type_raw in valid_exec
            else "",
            "playbook_log_status_choices": [c.value for c in AutomationExecutionLog.Status],
            "playbook_log_execution_type_choices": [
                c.value for c in AutomationExecutionLog.ExecutionType
            ],
            "playbook_log_playbook_slug_filter": playbook_log_playbook_slug_filter,
            "playbook_hub_clear_playbook_slug_url": playbook_hub_clear_playbook_slug_url,
            "playbook_slug_filter_links": playbook_slug_filter_links,
            "recent_logs": recent_logs,
            "operator_links": operator_links,
            "migration_playbooks": migration_playbooks,
            "playbook_hub_export_csv_url": playbook_hub_export_csv_url,
            "decision_architecture": get_decision_architecture_for_page(
                "playbook_operator_hub"
            ),
        },
    )
