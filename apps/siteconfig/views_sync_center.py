# Phase G optional: Sync Center UI – list SyncConflict for school, resolve server/client/discard
import json
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
import logging

from django.http import JsonResponse

_logger = logging.getLogger(__name__)

from apps.accounts.decorators import login_required, permission_required
from apps.siteconfig.staff_context_redirects import redirect_staff_without_school
from apps.sync_engine.conflict_actions import (
    apply_resolution,
    bulk_resolve,
    field_comparison,
    may_resolve,
    resolve_sync_conflict_row,
)

# Back-compat alias for admin + tests that imported the view helper.
_resolve_sync_conflict = resolve_sync_conflict_row

_CONFLICT_PAGE_SIZE = 25


#: How much history the live panel carries. Small on purpose — this is an at-a-glance
#: trust surface polled every few seconds, not an audit export (the admin changelist and
#: the ledger are there for that), so the payload must stay cheap.
_STATUS_RUN_LIMIT = 12
_STATUS_RECORD_LIMIT = 25
_STATUS_WINDOW_HOURS = 24


def _run_row(run, now) -> dict:
    """One EdgeSyncRun as the panel needs it, with the age precomputed server-side.

    ``age_seconds`` is derived here rather than in the browser because a box and a
    laptop rarely agree on the clock, and "last synced 4 seconds ago" computed against a
    skewed client clock is exactly the kind of quietly-wrong number that destroys trust
    in the whole panel.
    """
    finished = run.finished_at or run.created_at
    duration_ms = None
    if run.started_at and run.finished_at:
        duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
    return {
        "id": run.pk,
        "ok": bool(run.ok),
        "mode": run.mode,
        "pushed": run.pushed,
        "pulled": run.pulled,
        "conflicts": run.conflicts,
        "created": run.created,
        "upserted": run.upserted,
        # Rows the cycle REMOVED. Surfaced separately from every other count because it
        # is the only one that destroys data — an operator has to be able to see, at a
        # glance, that a cycle deleted things.
        "deleted": getattr(run, "deleted", 0) or 0,
        # Rows the cycle RECEIVED but could not apply. Carried separately from `pulled`
        # (a received count) because a pull that refused every row would otherwise render
        # as a perfectly healthy green cycle.
        "skipped": getattr(run, "skipped", 0) or 0,
        "message": run.message or "",
        "error": run.error or "",
        "finished_at": finished.isoformat() if finished else None,
        "age_seconds": int((now - finished).total_seconds()) if finished else None,
        "duration_ms": duration_ms,
    }


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
    # Attach the aligned field-by-field comparison and whether THIS viewer may settle
    # the conflict in the client's favour. Both are computed here rather than in the
    # template because the template cannot call a function with arguments — and a button
    # that is going to be refused should not be offered in the first place (the same
    # lesson as the admin index: a control that exists only to refuse you is worse than
    # no control).
    conflict_rows = list(page_obj.object_list)
    for _c in conflict_rows:
        try:
            _c.field_rows = field_comparison(_c)
            _c.may_keep_client, _c.keep_client_refusal = may_resolve(
                request.user, _c, "client"
            )
        except Exception:  # noqa: BLE001 — a display aid must never break the page
            _logger.debug("could not build the conflict comparison", exc_info=True)
            _c.field_rows = []
            _c.may_keep_client, _c.keep_client_refusal = True, ""
    return render(
        request,
        "siteconfig/sync_center.html",
        {
            **empty_ctx,
            "conflicts": conflict_rows,
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
    # WHY, captured with the decision. resolution_note is the audit trail alongside
    # resolved_by/resolved_at, and a resolution nobody can explain later is not a
    # resolution — especially on a money or grade record.
    note = (request.POST.get("note") or "").strip()[:255]
    ok, reason = apply_resolution(conflict, resolution_str, request.user, note=note)
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


def _sync_live_strings() -> dict:
    """Every user-visible string the live panel renders from JS, translated."""
    from django.utils.translation import gettext

    return {
        "never": gettext("never"),
        "just_now": gettext("just now"),
        "ago": gettext("ago"),
        "in_prefix": gettext("in "),
        "imminent": gettext("any moment"),
        # Compact duration suffixes; kept separate so a locale can drop the space or
        # use its own abbreviations.
        "unit_s": gettext("s"),
        "unit_m": gettext("m"),
        "unit_h": gettext("h"),
        "unit_d": gettext("d"),
        "unit_ms": gettext("ms"),
        "not_applied": gettext("Not applied"),
        "explain_schema_behind": gettext(
            "This box is behind on database migrations, so records using newer fields "
            "cannot be applied. Run migrations on the box; sync resumes automatically. "
            "Pending: "
        ),
        "explain_skipped": gettext(
            "Some records could not be applied on this box - most often a record that "
            "references a parent this box has not received yet. They are named in the "
            "cycle detail below and are retried automatically."
        ),
        "dir_down": gettext("cloud → box"),
        "dir_up": gettext("box → cloud"),
        "ok": gettext("OK"),
        "failed": gettext("failed"),
        "connected": gettext("Connected"),
        "offline": gettext("Offline"),
        "unknown": gettext("Link unknown"),
        "cloud_side": gettext("Cloud side"),
        "box_calls_out": gettext("Box calls out"),
        "state_hot": gettext("Keeping up"),
        "state_backoff": gettext("Backing off"),
        "state_steady": gettext("Idle"),
        "state_pinned": gettext("Pinned schedule"),
        "status_unavailable": gettext("Status unavailable"),
        "explain_cloud": gettext(
            "This is the cloud side. The box calls out on its own schedule; queue a full "
            "resync and it collects it on the next connection."
        ),
        "explain_offline": gettext(
            "No connection to the cloud. Work continues locally and is queued. Last reached: "
        ),
        "explain_offline_tail": gettext(
            ". The box keeps checking cheaply and syncs the moment the link returns."
        ),
        "explain_backoff": gettext(
            "Recent attempts failed, so retries are spacing out. A restored connection "
            "cancels the wait immediately."
        ),
        "explain_hot": gettext(
            "Data is flowing, so the box is staying close behind — cycles run every few "
            "seconds while changes keep arriving."
        ),
        "explain_steady": gettext(
            "Connected and up to date. The box is idling on a relaxed schedule and will "
            "speed up the moment anything changes."
        ),
        "explain_status_error": gettext(
            "Could not read sync status just now. Syncing itself is unaffected — this "
            "panel will keep trying."
        ),
    }


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
        # Translated strings for the live panel's JS. Built with the ACTIVE-language
        # gettext (not the lazy one) because json_script has to serialise real strings —
        # a lazy proxy would raise, and hardcoding English in the .js would put the whole
        # panel outside the translation system.
        "sync_live_strings": _sync_live_strings(),
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
    try:
        from apps.sync_engine.connectivity_probe import connectivity_snapshot

        ctx["edge_connectivity"] = connectivity_snapshot()
    except Exception:  # noqa: BLE001
        ctx["edge_connectivity"] = {}

    # The tenant's schedule: the existing rules, a blank form to add one, and the summary
    # (next run, last run, whether a window was missed) from schedule_policy — the same
    # code the scheduler acts on, so the panel cannot promise a time the box will not keep.
    try:
        from apps.siteconfig.forms_sync_schedule import SyncScheduleForm
        from apps.sync_engine import schedule_policy
        from apps.sync_engine.models_schedule import SyncSchedule
        from apps.sync_engine.schedule import describe_rule

        rows = list(SyncSchedule.objects.filter(school=school))
        for row in rows:
            row.human = describe_rule(row.to_rule())
            row.form = SyncScheduleForm(instance=row)
        ctx["sync_schedule_rules"] = rows
        ctx["sync_schedule_new_form"] = SyncScheduleForm(instance=SyncSchedule(school=school))
        ctx["sync_schedule_summary"] = schedule_policy.schedule_summary(school)
        ctx["sync_schedule_save_url"] = _safe_sync_reverse("siteconfig:sync_schedule_save")
    except Exception:  # noqa: BLE001 — an unmigrated box must still render the page
        _logger.debug("sync schedule panel context failed", exc_info=True)
        ctx["sync_schedule_rules"] = []
        ctx["sync_schedule_new_form"] = None
        ctx["sync_schedule_summary"] = None
        ctx["sync_schedule_save_url"] = None
    return ctx


@login_required
@require_http_methods(["GET", "POST"])
def sync_center_probe(request):
    """JSON HTTP probe for cloud pull/push — Sync Center “Test cloud connection”."""
    from django.conf import settings

    from apps.accounts.decorators import user_has_permission

    school = getattr(request, "school", None)
    if not school:
        return JsonResponse({"ok": False, "error": "No school"}, status=403)
    edge_enabled = bool(getattr(settings, "RMC_EDGE_SYNC_ENABLED", False))
    if not edge_enabled and not user_has_permission(
        request.user, school=school, codes="settings.manage"
    ):
        return JsonResponse({"ok": False, "error": "Forbidden"}, status=403)
    try:
        from apps.sync_engine.connectivity_probe import probe_cloud_http

        payload = probe_cloud_http()
    except Exception as exc:  # noqa: BLE001
        return JsonResponse(
            {"ok": False, "error": "probe_failed", "detail": str(exc)[:240]},
            status=503,
        )
    status = 200 if payload.get("ok") else 503
    return JsonResponse(payload, status=status)


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
    note = (body.get("note") or request.POST.get("note") or "").strip()[:255]
    result = bulk_resolve(
        school=school,
        ids=ids,
        resolution=resolution,
        resolved_by=request.user,
        entity_type=entity_type,
        note=note,
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
    # Without this the view returns None and Django raises
    # "didn't return an HttpResponse object" - a 500 on EVERY XHR "Sync now" click, which
    # is the only path the button actually uses (the form holds the tab open to watch
    # live progress). The non-XHR branch above returns a redirect, so the bug was
    # invisible to anything that submitted the form normally.
    return JsonResponse(payload)


@login_required
@require_http_methods(["GET"])
def sync_center_status(request):
    """Live sync evidence as JSON — the payload the Sync Center panel polls.

    WHY THIS EXISTS. The Sync Center rendered ONE row of counters and then went stale
    until someone reloaded, so "did the sync actually work?" was unanswerable without a
    refresh reflex. Worse, the numbers it did show (pushed/pulled totals) are summaries:
    they cannot distinguish "12 rows moved" from "the same row bounced 12 times", and a
    zero is ambiguous between "nothing to do" and "nothing happened".

    So this returns three different KINDS of evidence, because no single one is proof:

      * ``link`` + ``cadence`` — is the box connected, and when will it act next. Answers
        "is it working" BEFORE anything has moved, which is the state operators are in
        most of the time.
      * ``latest_run`` / ``recent_runs`` / ``totals`` — did cycles run, did they succeed,
        what did they carry. The audit trail.
      * ``recent_records`` — the actual ROWS that landed, from ``SyncApplyLedger``:
        entity, primary key, direction, when. This is the receipt. A count can be
        fabricated by a bug; a list of records you can go and look at cannot.

    Read-only and never raises: every section degrades to a null/empty value rather than
    500-ing an observability endpoint, because a broken status panel must not be
    indistinguishable from a broken sync.
    """
    from django.conf import settings
    from django.utils import timezone

    from apps.accounts.decorators import user_has_permission

    school = getattr(request, "school", None)
    if not school:
        return JsonResponse({"ok": False, "error": "No school"}, status=403)

    edge_enabled = bool(getattr(settings, "RMC_EDGE_SYNC_ENABLED", False))
    if not edge_enabled and not user_has_permission(
        request.user, school=school, codes="settings.manage"
    ):
        return JsonResponse({"ok": False, "error": "Forbidden"}, status=403)

    try:
        from apps.sync_engine.sync_status import serialize_live_status

        payload = serialize_live_status(school)
    except Exception:  # noqa: BLE001 — polling must fail explicitly, never as HTML/500
        return JsonResponse({"ok": False, "error": "status_unavailable"}, status=503)

    now = timezone.now()
    payload.update({
        "ok": True,
        "generated_at": now.isoformat(),
        "edge_sync_enabled": edge_enabled,
        "link": None,
        "cadence": None,
        "latest_run": None,
        "recent_runs": [],
        "recent_records": [],
        "totals": {},
        "pending_conflicts": None,
        # Whether THIS deployment's schema is current. A box behind on migrations cannot
        # apply rows for the new columns, and the raw OperationalError names a column,
        # never the cause.
        "schema": None,
    })

    try:
        from apps.sync_engine import schema_guard

        payload["schema"] = schema_guard.summary()
    except Exception:  # noqa: BLE001
        _logger.debug("schema summary failed for the status poll", exc_info=True)

    # The tenant's schedule and — the part people actually came for — WHEN THE NEXT SYNC
    # IS. Computed by schedule_policy, which is the same code the scheduler acts on, so
    # the label and the behaviour cannot drift apart.
    try:
        from apps.sync_engine import schedule_policy

        payload["schedule"] = schedule_policy.schedule_summary(school, now=now)
    except Exception:  # noqa: BLE001 — a schedule panel must never break the poll
        _logger.debug("schedule summary failed for the status poll", exc_info=True)
        payload["schedule"] = None

    try:
        from apps.sync_engine.connectivity_probe import connectivity_snapshot

        payload["connectivity"] = connectivity_snapshot()
    except Exception:  # noqa: BLE001 — evidence is additive to the canonical phase
        payload["connectivity"] = None

    try:
        from apps.sync_engine import cadence as _cadence
        from apps.sync_engine import connectivity as _connectivity

        payload["cadence"] = _cadence.snapshot()
        link = _connectivity.snapshot()
        last_online = link.get("last_online_at")
        link["seconds_since_online"] = (
            int(now.timestamp() - last_online) if last_online else None
        )
        payload["link"] = link
    except Exception:  # noqa: BLE001 — observability must not break on a helper
        pass

    try:
        from apps.sync_engine.models import EdgeSyncRun

        runs = list(EdgeSyncRun.objects.filter(school=school)[:_STATUS_RUN_LIMIT])
        payload["recent_runs"] = [_run_row(r, now) for r in runs]
        payload["latest_run"] = payload["recent_runs"][0] if payload["recent_runs"] else None

        window_start = now - timedelta(hours=_STATUS_WINDOW_HOURS)
        window = EdgeSyncRun.objects.filter(school=school, created_at__gte=window_start)
        agg = window.aggregate(
            runs=Count("id"),
            pushed=Sum("pushed"),
            pulled=Sum("pulled"),
            conflicts=Sum("conflicts"),
            skipped=Sum("skipped"),
            deleted=Sum("deleted"),
            failed=Count("id", filter=Q(ok=False)),
        )
        payload["totals"] = {
            "window_hours": _STATUS_WINDOW_HOURS,
            "runs": agg.get("runs") or 0,
            "pushed": agg.get("pushed") or 0,
            "pulled": agg.get("pulled") or 0,
            "conflicts": agg.get("conflicts") or 0,
            "skipped": agg.get("skipped") or 0,
            # Deletions now cross the boundary (G1). This is the one total whose meaning
            # is "records were destroyed", so it gets its own number rather than hiding
            # inside `pulled` — the same reasoning that gave `skipped` a tile.
            "deleted": agg.get("deleted") or 0,
            "failed": agg.get("failed") or 0,
        }
    except Exception:  # noqa: BLE001
        pass

    try:
        from apps.sync_engine.models import SyncApplyLedger

        rows = list(
            SyncApplyLedger.objects.filter(school=school).order_by("-applied_at")[
                :_STATUS_RECORD_LIMIT
            ]
        )
        payload["recent_records"] = [
            {
                "entity_type": row.entity_type,
                "local_pk": row.local_pk,
                # "cloud-pull" (came down) vs "edge-push" (went up) — the direction is
                # what makes this a receipt rather than a count.
                "origin": row.origin or "",
                "applied_at": row.applied_at.isoformat() if row.applied_at else None,
                "age_seconds": (
                    int((now - row.applied_at).total_seconds()) if row.applied_at else None
                ),
            }
            for row in rows
        ]
    except Exception:  # noqa: BLE001
        pass

    try:
        from .models import SyncConflict

        payload["pending_conflicts"] = SyncConflict.objects.filter(
            school=school, status=SyncConflict.Status.PENDING
        ).count()
    except Exception:  # noqa: BLE001
        pass

    return JsonResponse(payload)


# --------------------------------------------------------------- schedule editor --
@login_required
@permission_required("settings.manage")
@require_http_methods(["POST"])
def sync_schedule_save(request):
    """Create or update one sync-schedule rule for ``request.school``.

    WHY THE SCHOOL COMES FROM THE REQUEST AND NEVER THE FORM. The rule decides when a box
    talks to the cloud; accepting a ``school`` from POST would let anyone who can reach
    this endpoint retime another tenant's box. The instance is re-fetched scoped to
    ``request.school`` for the same reason — an id in a URL is an argument, not a claim.

    PROPAGATION IS STATED, NOT IMPLIED. The cloud cannot open a connection to a box, so a
    saved change lands on the box's NEXT cycle. Saying "Saved" alone would leave the
    operator watching for something that is minutes away by design, and that gap is where
    people conclude sync is broken.
    """
    school = getattr(request, "school", None)
    if not school:
        return redirect_staff_without_school(
            request, message=_("Select your school to change the sync schedule.")
        )

    from apps.siteconfig.forms_sync_schedule import SyncScheduleForm
    from apps.sync_engine.models_schedule import SyncSchedule

    back = _safe_sync_reverse("siteconfig:sync_center") or "/"
    rule_id = (request.POST.get("rule_id") or "").strip()
    instance = None
    if rule_id.isdigit():
        instance = SyncSchedule.objects.filter(pk=int(rule_id), school=school).first()
        if instance is None:
            messages.error(request, _("That sync schedule rule no longer exists."))
            return redirect(back)

    if (request.POST.get("action") or "").strip() == "delete":
        if instance is not None:
            instance.delete()
            messages.success(request, _("Sync schedule rule removed."))
            _wake_for_schedule_change(school)
        return redirect(back)

    form = SyncScheduleForm(request.POST, instance=instance or SyncSchedule(school=school))
    if not form.is_valid():
        # Surface the field-level reason rather than a generic failure: "this rule can
        # never run" is only useful attached to the control that caused it.
        for field, errors in form.errors.items():
            label = form.fields[field].label if field in form.fields else ""
            for error in errors:
                messages.error(request, f"{label}: {error}" if label else str(error))
        return redirect(back)

    rule = form.save(commit=False)
    rule.school = school
    rule.save()
    _wake_for_schedule_change(school)
    messages.success(
        request,
        _(
            "Sync schedule saved. It takes effect on the box at its next sync — the cloud "
            "cannot contact a box directly."
        ),
    )
    return redirect(back)


def _wake_for_schedule_change(school):
    """Nudge the box so a schedule change is picked up on the next tick, not the next hour.

    Best effort by design: a failure here costs latency, never the saved rule. On the
    cloud this bumps the change beacon so a box holding the long-poll open returns
    immediately; on a box it raises the local cadence wake.
    """
    try:
        from apps.sync_engine import cadence

        cadence.request_wake("sync schedule changed")
    except Exception:  # noqa: BLE001 — never fail a save on the nudge
        _logger.debug("schedule change wake failed", exc_info=True)
    try:
        from apps.sync_engine import change_beacon

        change_beacon.bump(getattr(school, "pk", school))
    except Exception:  # noqa: BLE001
        _logger.debug("schedule change beacon failed", exc_info=True)
