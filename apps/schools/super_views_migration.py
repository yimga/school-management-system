"""
Super Admin views: migration cloud, profile registry, rollback, and sync repair.
Extracted from super_views for giant-file decomposition; re-exported by super_views for URL wiring.
"""
from datetime import timedelta

from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST
from django.http import JsonResponse
from django.utils import timezone

from django.core.exceptions import ValidationError
from django.db import DatabaseError

from .models import School

CONTROL_PLANE_AUDIT_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    TypeError,
    ValidationError,
    ValueError,
)


def super_migration_cloud(request):
    """Migration cloud pillar: control-plane governance for profiles, runs, parity, and rollback."""
    from apps.accounts.migration_services import compute_parity
    from apps.automation.models import MigrationProfile, MigrationRun
    from apps.siteconfig.migration_services import dry_run_import

    profile_slug = (request.GET.get("profile") or "").strip()
    school_id = (request.GET.get("school_id") or "").strip()
    selected_school = None
    if school_id:
        try:
            selected_school = School.objects.filter(id=school_id).first()
        except (TypeError, ValueError):
            selected_school = None
    selected_profile = MigrationProfile.objects.filter(slug=profile_slug, is_active=True).first() if profile_slug else None

    profiles = list(MigrationProfile.objects.filter(is_active=True).order_by("sort_order", "slug"))
    recent_runs = list(
        MigrationRun.objects.select_related("school", "triggered_by")
        .order_by("-started_at")[:40]
    )
    for run in recent_runs:
        run.parity = compute_parity(run)

    rollback_candidates = [run for run in recent_runs if run.can_rollback]
    preview = None
    if selected_profile is not None:
        preview = dry_run_import(selected_profile, {"rows": [], "mapping": {}}, school=selected_school)

    summary = {
        "profiles_total": len(profiles),
        "runs_total": MigrationRun.objects.count(),
        "runs_last_30d": MigrationRun.objects.filter(started_at__gte=timezone.now() - timedelta(days=30)).count(),
        "failed_last_30d": MigrationRun.objects.filter(
            started_at__gte=timezone.now() - timedelta(days=30),
            status=MigrationRun.Status.FAILED,
        ).count(),
        "rollback_ready": MigrationRun.objects.filter(
            dry_run=False,
            rolled_back_by_run__isnull=True,
            rollback_snapshot__isnull=False,
        ).exclude(rollback_snapshot={}).count(),
    }

    return render(
        request,
        "schools/super_migration_cloud.html",
        {
            "summary": summary,
            "profiles": profiles,
            "recent_runs": recent_runs,
            "rollback_candidates": rollback_candidates[:10],
            "selected_school": selected_school,
            "selected_profile": selected_profile,
            "preview": preview,
            "dashboard_url": reverse("super:dashboard"),
            "registry_url": reverse("super:migration_profile_registry"),
        },
    )


def super_migration_profile_registry(request):
    """Migration Profile Registry: list profiles grouped by source_system and profile_category."""
    from apps.automation.models import MigrationProfile
    from itertools import groupby

    profiles = list(
        MigrationProfile.objects.filter(is_active=True).order_by("source_system", "profile_category", "sort_order", "slug")
    )
    groups = []
    for key, grp in groupby(profiles, key=lambda p: (p.source_system or "generic", p.profile_category or "uncategorized")):
        source_system, profile_category = key
        groups.append((source_system, profile_category, list(grp)))
    migration_cloud_url = reverse("super:migration_cloud")
    return render(
        request,
        "schools/super_migration_profile_registry.html",
        {
            "registry_groups": groups,
            "migration_cloud_url": migration_cloud_url,
            "dashboard_url": reverse("super:dashboard"),
            "profiles_total": len(profiles),
            "groups_count": len(groups),
        },
    )


@require_POST
def super_migration_rollback(request, run_id):
    from apps.automation.models import MigrationRun

    run = get_object_or_404(MigrationRun.objects.select_related("school"), pk=run_id)
    rollback_run, result = run.trigger_rollback(user=getattr(request, "user", None))
    if str(request.content_type or "").startswith("application/json"):
        status = 200 if result.get("success") else 400
        return JsonResponse(
            {
                "ok": bool(result.get("success")),
                "run_id": run.pk,
                "rollback_run_id": getattr(rollback_run, "pk", None),
                **result,
            },
            status=status,
        )
    if result.get("success"):
        messages.success(request, result.get("message") or "Rollback completed.")
    else:
        messages.error(request, result.get("message") or "Rollback failed.")
    return redirect("super:migration_cloud")


def _sync_repair_force_overwrite_conflict(conflict, resolved_by):
    """Apply client_data to entity and mark conflict RESOLVED_CLIENT. Call inside transaction.atomic()."""
    from apps.api.sync_services import _get_entity_config

    conflict.resolved_by = resolved_by
    conflict.resolved_at = timezone.now()
    conflict.status = "RESOLVED_CLIENT"
    config = _get_entity_config()
    if conflict.entity_type in config:
        model, allowed = config[conflict.entity_type]
        updates = {k: v for k, v in (conflict.client_data or {}).items() if k in allowed}
        if updates:
            try:
                instance = model.objects.get(pk=conflict.entity_id)
                for key, value in updates.items():
                    setattr(instance, key, value)
                update_fields = list(updates.keys())
                if hasattr(instance, "updated_at"):
                    update_fields.append("updated_at")
                instance.save(update_fields=update_fields)
            except model.DoesNotExist:
                pass
    conflict.save(update_fields=["status", "resolved_at", "resolved_by"])


@require_http_methods(["GET", "POST"])
def sync_repair(request, school_id):
    """
    Phase G: Super Admin Emergency Sync Repair. List SyncConflict for a school;
    side-by-side client vs server; Force Overwrite applies client_data with transaction.atomic().
    """
    from django.db import transaction
    from apps.siteconfig.models import SyncConflict

    school = get_object_or_404(School, pk=school_id)
    if not (getattr(request.user, "is_superuser", False)):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Superuser required for Sync Repair.")

    if request.method == "POST":
        conflict_id = request.POST.get("conflict_id")
        if conflict_id:
            try:
                conflict = SyncConflict.objects.get(pk=int(conflict_id), school_id=school_id, status=SyncConflict.Status.PENDING)
            except (ValueError, SyncConflict.DoesNotExist):
                messages.error(request, "Conflict not found or already resolved.")
            else:
                with transaction.atomic():
                    _sync_repair_force_overwrite_conflict(conflict, request.user)
                try:
                    from apps.schools.control_plane import log_control_plane_action
                    from apps.compliance.models_audit import AuditLog
                    log_control_plane_action(
                        request,
                        AuditLog.Action.UPDATE,
                        "SyncConflict",
                        str(conflict.pk),
                        object_repr=f"SyncConflict #{conflict.pk} ({conflict.entity_type})",
                        reason="Sync repair force overwrite (client applied)",
                        sensitivity=AuditLog.Sensitivity.HIGH,
                        new_values={"status": "RESOLVED_CLIENT", "school_id": str(school_id)},
                    )
                except CONTROL_PLANE_AUDIT_FAILURES:
                    pass
                messages.success(request, f"Conflict #{conflict_id} resolved (client version applied).")
            return redirect("super:sync_repair", school_id=school_id)

    conflicts = list(
        SyncConflict.objects.filter(school_id=school_id)
        .select_related("reported_by")
        .order_by("-created_at")[:100]
    )
    return render(
        request,
        "schools/super_sync_repair.html",
        {"school": school, "conflicts": conflicts, "dashboard_url": reverse("super:dashboard")},
    )
