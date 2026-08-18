# Phase G optional: Sync Center UI – list SyncConflict for school, resolve server/client/discard
from django.contrib import messages
from django.db.models import Q, Count
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse

from apps.accounts.decorators import login_required, permission_required
from apps.siteconfig.staff_context_redirects import redirect_staff_without_school


def _safe_sync_reverse(name: str):
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


def _resolve_sync_conflict(conflict, resolution, resolved_by):
    from django.utils import timezone
    from .models import SyncConflict

    conflict.resolved_by = resolved_by
    conflict.resolved_at = timezone.now()
    conflict.status = resolution
    if resolution == SyncConflict.Status.RESOLVED_CLIENT:
        from apps.api.sync_services import _get_entity_config

        # Resolving an edge-sync conflict is itself an edge-scoped operation, so it must
        # use the FULL two-way registry — otherwise "keep client version" silently writes
        # NOTHING for a derived entity (applicant/student_note/academic_year/term/department)
        # while still stamping the record RESOLVED_CLIENT (the operator is told the client
        # won but the server value is kept). See _get_entity_config(include_derived=...).
        config = _get_entity_config(include_derived=True)
        if conflict.entity_type in config:
            model, allowed = config[conflict.entity_type]
            updates = {
                k: v for k, v in (conflict.client_data or {}).items() if k in allowed
            }
            if updates:
                try:
                    instance = model.objects.get(pk=conflict.entity_id)
                    for key, value in updates.items():
                        setattr(instance, key, value)
                    instance.save(update_fields=list(updates.keys()) + ["updated_at"])
                except model.DoesNotExist:
                    pass
    conflict.save(update_fields=["status", "resolved_at", "resolved_by"])


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET"])
def sync_center(request):
    """List SyncConflict for request.school; link to resolve from UI or admin."""
    school = getattr(request, "school", None)
    if not school:
        return redirect_staff_without_school(
            request,
            message="Select your school to view sync conflicts.",
        )
    pref_url = reverse("siteconfig:user_preferences")
    # Edge<->cloud sync status panel context (feature ②). Never let a missing model /
    # stray error on this observability read break the conflicts page.
    panel = _edge_sync_panel_context(school)
    try:
        from .models import SyncConflict
    except ImportError:
        return render(
            request,
            "siteconfig/sync_center.html",
            {
                "school": school,
                "conflicts": [],
                "sync_available": False,
                "action_url": pref_url,
                "action_text": _("Back to preferences"),
                "sync_stats_total": 0,
                "sync_stats_pending": 0,
                "scheduled_hub_url": _safe_sync_reverse(
                    "siteconfig:scheduled_reports_delivery_hub"
                ),
                "console_url": _safe_sync_reverse("siteconfig:console_domains_hub"),
                "admin_sync_conflict_url": None,
                **panel,
            },
        )
    stats = (
        SyncConflict.objects.filter(school=school)
        .aggregate(
            total=Count("id"),
            pending=Count(
                "id", filter=Q(status=SyncConflict.Status.PENDING)
            ),
        )
    )
    conflicts = SyncConflict.objects.filter(school=school).order_by("-created_at")[:50]
    admin_sync_url = None
    if getattr(request.user, "is_superuser", False):
        try:
            admin_sync_url = reverse("admin:siteconfig_syncconflict_changelist")
        except NoReverseMatch:
            admin_sync_url = None
    return render(
        request,
        "siteconfig/sync_center.html",
        {
            "school": school,
            "conflicts": conflicts,
            "sync_available": True,
            "action_url": pref_url,
            "action_text": _("Back to preferences"),
            "sync_stats_total": stats.get("total") or 0,
            "sync_stats_pending": stats.get("pending") or 0,
            "scheduled_hub_url": _safe_sync_reverse(
                "siteconfig:scheduled_reports_delivery_hub"
            ),
            "console_url": _safe_sync_reverse("siteconfig:console_domains_hub"),
            "admin_sync_conflict_url": admin_sync_url,
            **panel,
        },
    )


@login_required
@permission_required("settings.manage")
@require_http_methods(["POST"])
def sync_center_resolve(request, conflict_id):
    """Resolve one conflict: resolution=server|client|discard."""
    school = getattr(request, "school", None)
    if not school:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "No school"}, status=403)
        return redirect_staff_without_school(
            request,
            message="Select your school to resolve sync conflicts.",
        )
    try:
        from .models import SyncConflict
    except ImportError:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {"ok": False, "error": "SyncConflict not available"}, status=404
            )
        return redirect("siteconfig:sync_center")
    conflict = get_object_or_404(SyncConflict, pk=conflict_id, school=school)
    if conflict.status != SyncConflict.Status.PENDING:
        messages.info(request, "Conflict already resolved.")
        return redirect("siteconfig:sync_center")
    resolution_str = (request.POST.get("resolution") or "").strip().lower()
    if resolution_str == "server":
        resolution = SyncConflict.Status.RESOLVED_SERVER
    elif resolution_str == "client":
        resolution = SyncConflict.Status.RESOLVED_CLIENT
    elif resolution_str == "discard":
        resolution = SyncConflict.Status.DISCARDED
    else:
        messages.error(request, "Invalid resolution.")
        return redirect("siteconfig:sync_center")
    _resolve_sync_conflict(conflict, resolution, request.user)
    messages.success(request, f"Conflict resolved ({resolution_str}).")
    return redirect("siteconfig:sync_center")


def _edge_sync_panel_context(school):
    """Shared Sync Center panel context for both render paths.

    ``edge_sync_enabled`` distinguishes the two deployments this ONE page serves, and the
    distinction is not cosmetic — it decides which actions are even physically possible:

      * On a BOX (flag on) the box can call out, so "Sync now" / "Dry-run sync" work.
      * On the CLOUD (flag off — its normal, correct state) the box sits behind NAT and
        the cloud cannot open a connection to it. Offering "Sync now" there produced a
        guaranteed failure on every click plus a red EdgeSyncRun row; what the cloud can
        actually do is QUEUE a full-resync the box collects on its next poll.

    Everything here is best-effort: the conflicts page must still render if the sync
    models are unavailable.
    """
    from django.conf import settings

    ctx = {
        "edge_sync_enabled": bool(getattr(settings, "RMC_EDGE_SYNC_ENABLED", False)),
        "latest_sync_run": None,
        "pending_resync": None,
        "last_served_resync": None,
        "sync_interval_seconds": None,
    }
    try:
        from apps.sync_engine.edge_scheduler import edge_sync_interval_seconds
        from apps.sync_engine.models import EdgeSyncDirective, EdgeSyncRun

        ctx["latest_sync_run"] = EdgeSyncRun.latest_for(school)
        ctx["sync_interval_seconds"] = edge_sync_interval_seconds()
        directives = EdgeSyncDirective.objects.filter(
            school=school, kind=EdgeSyncDirective.FULL_RESYNC
        )
        ctx["pending_resync"] = directives.filter(served_at__isnull=True).first()
        ctx["last_served_resync"] = directives.filter(served_at__isnull=False).first()
    except Exception:  # noqa: BLE001 — panel is observability; never break the page
        pass
    return ctx


@login_required
@permission_required("settings.manage")
@require_http_methods(["POST"])
def sync_request_resync(request):
    """Queue a full resync for this school's edge box (cloud-side action).

    The honest cloud->box control: the cloud records the request and the box acts on it
    the next time it calls out. Safe to press while the box is offline — the directive
    simply waits, and pressing again does not queue a second one.
    """
    school = getattr(request, "school", None)
    if not school:
        return redirect_staff_without_school(
            request,
            message="Select your school to request a resync.",
        )
    try:
        from apps.sync_engine.models import request_full_resync

        directive = request_full_resync(school, request.user)
    except Exception:  # noqa: BLE001 — surface as a message, never a 500
        messages.error(request, _("Could not queue the resync request."))
        return redirect("siteconfig:sync_center")
    if directive.served_at is None:
        messages.success(
            request,
            _(
                "Full resync queued. The box replays every record the next time it "
                "connects — it does not need to be online right now."
            ),
        )
    else:
        messages.info(request, _("A resync was already queued."))
    return redirect("siteconfig:sync_center")


@login_required
@permission_required("settings.manage")
@require_http_methods(["POST"])
def sync_now(request):
    """Run one edge<->cloud sync cycle now, from the Sync Center button.

    Self-healing wrapper: ``run_sync_cycle`` never raises and always records one
    ``EdgeSyncRun``, so a network outage or a disabled deployment surfaces as a flash
    message and a visible run row rather than a crashed page. ``mode`` defaults to
    ``dry`` — a no-write connectivity check (neither pushes nor applies) — for safety;
    ``mode=live`` performs the full push-up-then-pull-down-and-apply cycle.
    """
    school = getattr(request, "school", None)
    if not school:
        return redirect_staff_without_school(
            request,
            message="Select your school to run a sync.",
        )
    from django.conf import settings

    from apps.sync_engine import sync_runner

    # Refuse BEFORE recording anything on a deployment that cannot perform this action.
    # The box-initiated cycle is meaningless on the cloud (there is no operator for the
    # cloud to call out to, and it cannot reach into the box's LAN), so running it here
    # only manufactured a red run row on every click. Point the operator at the control
    # that does work from this side.
    if not bool(getattr(settings, "RMC_EDGE_SYNC_ENABLED", False)):
        messages.error(
            request,
            _(
                "This deployment does not run edge sync. A box on a private network "
                "cannot be reached from the cloud — it syncs by calling out on its own "
                "schedule. Use “Queue full resync” to have it replay everything "
                "on its next connection."
            ),
        )
        return redirect("siteconfig:sync_center")

    mode = "live" if (request.POST.get("mode") or "").strip().lower() == "live" else "dry"
    result = sync_runner.run_sync_cycle(school, mode=mode)
    if not result.get("enabled", True):
        messages.error(request, result.get("message") or "Edge sync is not enabled.")
    elif result.get("ok"):
        messages.success(
            request,
            _("Sync complete (%(mode)s): pushed %(pushed)s, pulled %(pulled)s, "
              "conflicts %(conflicts)s.")
            % {
                "mode": result["mode"],
                "pushed": result["pushed"],
                "pulled": result["pulled"],
                "conflicts": result["conflicts"],
            },
        )
    else:
        messages.error(
            request,
            _("Sync finished with errors (%(mode)s): %(error)s")
            % {"mode": result["mode"], "error": result.get("error") or result.get("message") or ""},
        )
    return redirect("siteconfig:sync_center")
