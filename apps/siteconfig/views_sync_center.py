# Phase G optional: Sync Center UI – list SyncConflict for school, resolve server/client/discard
import json

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse

from apps.accounts.decorators import login_required, permission_required
from apps.siteconfig.staff_context_redirects import redirect_staff_without_school
from apps.sync_engine.conflict_actions import (
    apply_resolution,
    bulk_resolve,
    resolve_sync_conflict_row,
)

# Back-compat alias for admin + tests that imported the view helper.
_resolve_sync_conflict = resolve_sync_conflict_row

_CONFLICT_PAGE_SIZE = 25


def _safe_sync_reverse(name: str):
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


def _parse_json_body(request):
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return {}


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
    empty_ctx = {
        "school": school,
        "conflicts": [],
        "page_obj": None,
        "sync_available": False,
        "action_url": pref_url,
        "action_text": _("Back to preferences"),
        "sync_stats_total": 0,
        "sync_stats_pending": 0,
        "conflict_status_filter": "pending",
        "conflict_groups": [],
        "bulk_actions": _conflict_bulk_actions(),
        "scheduled_hub_url": _safe_sync_reverse(
            "siteconfig:scheduled_reports_delivery_hub"
        ),
        "console_url": _safe_sync_reverse("siteconfig:console_domains_hub"),
        "admin_sync_conflict_url": None,
        **panel,
    }
    try:
        from .models import SyncConflict
    except ImportError:
        return render(request, "siteconfig/sync_center.html", empty_ctx)
    stats = (
        SyncConflict.objects.filter(school=school)
        .aggregate(
            total=Count("id"),
            pending=Count(
                "id", filter=Q(status=SyncConflict.Status.PENDING)
            ),
        )
    )
    status_filter = (request.GET.get("status") or "pending").strip().lower()
    if status_filter not in {"pending", "all", "resolved"}:
        status_filter = "pending"
    qs = SyncConflict.objects.filter(school=school).order_by("-created_at")
    if status_filter == "pending":
        qs = qs.filter(status=SyncConflict.Status.PENDING)
    elif status_filter == "resolved":
        qs = qs.exclude(status=SyncConflict.Status.PENDING)
    entity_filter = (request.GET.get("entity_type") or "").strip()
    if entity_filter:
        qs = qs.filter(entity_type=entity_filter)
    paginator = Paginator(qs, _CONFLICT_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page") or 1)
    groups = list(
        SyncConflict.objects.filter(
            school=school, status=SyncConflict.Status.PENDING
        )
        .values("entity_type")
        .annotate(pending_count=Count("id"))
        .order_by("entity_type")
    )
    extra = request.GET.copy()
    extra.pop("page", None)
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
            **empty_ctx,
            "conflicts": list(page_obj.object_list),
            "page_obj": page_obj,
            "pagination_extra_query": extra.urlencode(),
            "sync_available": True,
            "sync_stats_total": stats.get("total") or 0,
            "sync_stats_pending": stats.get("pending") or 0,
            "conflict_status_filter": status_filter,
            "conflict_entity_filter": entity_filter,
            "conflict_groups": groups,
            "admin_sync_conflict_url": admin_sync_url,
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
    ok, reason = apply_resolution(conflict, resolution_str, request.user)
    if not ok:
        messages.error(request, reason or _("Invalid resolution."))
        return redirect("siteconfig:sync_center")
    messages.success(
        request,
        _("Conflict resolved (%(resolution)s).") % {"resolution": resolution_str},
    )
    return redirect("siteconfig:sync_center")


def _conflict_bulk_actions():
    return [
        {"slug": "server", "label": str(_("Keep server")), "variant": "default"},
        {"slug": "client", "label": str(_("Keep client")), "variant": "default"},
        {"slug": "policy", "label": str(_("Apply school policy")), "variant": "default"},
        {"slug": "discard", "label": str(_("Discard")), "variant": "danger"},
    ]


def _edge_sync_panel_context(school):
    """Shared Sync Center panel context for both render paths.

    ``edge_sync_enabled`` distinguishes the two deployments this ONE page serves, and the
    distinction is not cosmetic — it decides which actions are even physically possible:

      * On a BOX (flag on) the box can call out, so "Sync now" / "Dry-run sync" work.
      * On the CLOUD (flag off — its normal, correct state) the box sits behind NAT and
        the cloud cannot open a connection to it. Offering "Sync now" there produced a
        guaranteed failure on every click plus a red EdgeSyncRun row; what the cloud can
        actually do is QUEUE a full-resync the box collects on its next poll.

    Live phase comes from ``serialize_live_status`` so a queued resync is never
    hidden behind an older failed run. Best-effort: the conflicts page must
    still render if the sync models are unavailable.
    """
    from django.conf import settings

    ctx = {
        "edge_sync_enabled": bool(getattr(settings, "RMC_EDGE_SYNC_ENABLED", False)),
        "latest_sync_run": None,
        "pending_resync": None,
        "last_served_resync": None,
        "sync_interval_seconds": None,
        "sync_live": {},
    }
    try:
        from apps.sync_engine.models import EdgeSyncDirective, EdgeSyncRun
        from apps.sync_engine.sync_status import serialize_live_status

        ctx["sync_live"] = serialize_live_status(school)
        ctx["latest_sync_run"] = EdgeSyncRun.latest_for(school)
        ctx["sync_interval_seconds"] = ctx["sync_live"].get("sync_interval_seconds")
        ctx["edge_sync_enabled"] = bool(ctx["sync_live"].get("edge_sync_enabled"))
        pending_id = (ctx["sync_live"].get("pending_resync") or {}).get("id")
        served_id = (ctx["sync_live"].get("last_served_resync") or {}).get("id")
        if pending_id:
            ctx["pending_resync"] = EdgeSyncDirective.objects.filter(
                pk=pending_id, school=school
            ).first()
        if served_id:
            ctx["last_served_resync"] = EdgeSyncDirective.objects.filter(
                pk=served_id, school=school
            ).first()
    except Exception:  # noqa: BLE001 — panel is observability; never break the page
        pass
    return ctx


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET"])
def sync_center_status(request):
    """JSON snapshot of live edge-sync phase for the bound school."""
    school = getattr(request, "school", None)
    if not school:
        return JsonResponse({"ok": False, "error": "No school"}, status=403)
    try:
        from apps.sync_engine.sync_status import serialize_live_status

        payload = serialize_live_status(school)
    except Exception:  # noqa: BLE001 — poll must degrade, never 500 the page JS
        return JsonResponse({"ok": False, "error": "status_unavailable"}, status=503)
    payload["ok"] = True
    return JsonResponse(payload)


@login_required
@permission_required("settings.manage")
@require_http_methods(["POST"])
def sync_center_bulk_resolve(request):
    """Resolve many PENDING conflicts for request.school only."""
    school = getattr(request, "school", None)
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest" or (
        request.content_type or ""
    ).startswith("application/json")
    if not school:
        if wants_json:
            return JsonResponse({"ok": False, "error": "No school"}, status=403)
        return redirect_staff_without_school(
            request,
            message="Select your school to resolve sync conflicts.",
        )
    body = _parse_json_body(request)
    ids = body.get("ids") or request.POST.getlist("ids")
    resolution = (body.get("resolution") or request.POST.get("resolution") or "").strip()
    entity_type = (
        body.get("entity_type") or request.POST.get("entity_type") or ""
    ).strip()
    result = bulk_resolve(
        school=school,
        ids=ids,
        resolution=resolution,
        resolved_by=request.user,
        entity_type=entity_type,
    )
    if wants_json:
        return JsonResponse(result, status=200 if result.get("ok") else 400)
    if result.get("ok"):
        messages.success(request, result.get("message") or _("Conflicts resolved."))
    else:
        messages.error(request, result.get("message") or _("Could not resolve conflicts."))
    return redirect("siteconfig:sync_center")


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
    """Queue one edge<->cloud sync cycle from the Sync Center button.

    The HTTP worker opens the in-progress ``EdgeSyncRun`` then enqueues Celery so
    the same tab can poll live percent. ``run_sync_cycle`` never raises; eager
    tests still finish in-request. ``mode`` defaults to ``dry``; ``mode=live``
    is the full push-then-pull cycle.
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

    from apps.platform_runtime.workflow_telemetry import (
        background_job_payload,
        enqueue_background_job,
    )
    from apps.sync_engine.models import EdgeSyncRun
    from apps.sync_engine.tasks import run_sync_cycle_for_school_task

    already = EdgeSyncRun.in_progress_for(school)
    if already is not None:
        notice = _("A sync cycle is already running. Watch live progress on this page.")
        messages.info(request, notice)
        return _sync_now_reply(request, school, queued=True, message=notice)

    # Open the live row on the HTTP worker so the next status poll sees
    # **running** even before Celery picks the job up.
    run_row = EdgeSyncRun.begin(school, mode=mode)
    sync_runner._pulse_sync(
        school,
        processed=0,
        expected=2,
        log_message="Sync queued",
        status="running",
    )
    async_result = enqueue_background_job(
        run_sync_cycle_for_school_task,
        int(school.pk),
        block_in_process=False,
        mode=mode,
        run_id=int(run_row.pk),
    )
    result = background_job_payload(async_result)
    if isinstance(result, dict) and result.get("enabled") is False:
        messages.error(request, result.get("message") or _("Edge sync is not enabled."))
        return _sync_now_reply(request, school, result=result)
    if isinstance(result, dict) and "ok" in result:
        if result.get("ok"):
            messages.success(
                request,
                _(
                    "Sync complete (%(mode)s): pushed %(pushed)s, pulled %(pulled)s, "
                    "conflicts %(conflicts)s."
                )
                % {
                    "mode": result.get("mode") or mode,
                    "pushed": result.get("pushed") or 0,
                    "pulled": result.get("pulled") or 0,
                    "conflicts": result.get("conflicts") or 0,
                },
            )
        else:
            messages.error(
                request,
                _("Sync finished with errors (%(mode)s): %(error)s")
                % {
                    "mode": result.get("mode") or mode,
                    "error": result.get("error") or result.get("message") or "",
                },
            )
        return _sync_now_reply(request, school, result=result)

    started = _("Sync started. Watch live progress on this page.")
    messages.success(request, started)
    return _sync_now_reply(request, school, queued=True, message=started)


def _sync_now_reply(request, school, *, queued=False, message="", result=None):
    """JSON for hold-submit (same tab stays mounted); 302 for a normal POST."""
    xhr = (request.headers.get("X-Requested-With") or "") == "XMLHttpRequest"
    if not xhr:
        return redirect("siteconfig:sync_center")

    from apps.sync_engine.sync_status import serialize_live_status

    payload = serialize_live_status(school)
    payload["ok"] = True
    payload["accepted"] = True
    payload["queued"] = bool(queued) or payload.get("phase") == "running"
    if isinstance(result, dict):
        payload["result"] = {
            "ok": result.get("ok"),
            "mode": result.get("mode"),
            "pushed": result.get("pushed") or 0,
            "pulled": result.get("pulled") or 0,
            "conflicts": result.get("conflicts") or 0,
            "error": result.get("error") or "",
            "message": result.get("message") or "",
        }
    if message:
        payload["flash"] = str(message)
    return JsonResponse(payload)
