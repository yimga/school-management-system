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
from django.utils.timezone import now as dj_timezone_now

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

#: How many entity types the work queue names before it stops listing. The queue exists
#: to tell an operator the SHAPE of the backlog at a glance; a list long enough to scroll
#: has stopped doing that, and the full breakdown is one click away on the conflicts page.
_WORK_QUEUE_GROUP_LIMIT = 4

#: The strip's header row. Every third hour is numbered and the rest are blank — 24
#: numbers across a column that narrow is unreadable, and the shape is what is being read
#: anyway. Built here because a Django template cannot do modulo arithmetic on a range.
_STRIP_HOUR_LABEL_EVERY = 3
_STRIP_HOUR_LABELS = [
    str(hour) if hour % _STRIP_HOUR_LABEL_EVERY == 0 else ""
    for hour in range(24)  # magic-number-allow: hours in a day
]


#: How much history the live panel carries. Small on purpose — this is an at-a-glance
#: trust surface polled every few seconds, not an audit export (the admin changelist and
#: the ledger are there for that), so the payload must stay cheap.
_STATUS_RUN_LIMIT = 12
_STATUS_RECORD_LIMIT = 25
_STATUS_WINDOW_HOURS = 24

#: The windows the flow band can ask for. FETCHED ON DEMAND rather than computed on every
#: poll: the panel re-asks every few seconds and a second aggregate per tick is a real
#: cost on a box that is also trying to sync. Whichever window is selected is the only one
#: computed, and 24h stays the default because it is the one an operator opens the page
#: holding a question about.
_STATUS_WINDOW_CHOICES = {"24h": 24, "7d": 24 * 7}


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
    """The Sync Center: is it working, when does it run, what needs a human.

    WHAT CHANGED, AND WHY. This page used to carry six stacked cards -- edge sync,
    schedule, progress, live activity, conflicts, diagnostics -- each written to stand on
    its own, so each re-derived what its neighbour already showed. Five separate facts
    were rendered twice (last sync, next sync, recent cycles, pushed/pulled, the conflict
    count), and one of those pairs could legitimately DISAGREE: the schedule panel showed
    the next occurrence of a RULE while the live panel showed the next moment CADENCE was
    due. Both correct, different questions, and nothing on screen said so.

    The page is now three always-on bands (verdict, flow, schedule), one activity
    timeline, and a work queue that is absent when nothing needs a person. Conflicts
    moved to :func:`sync_conflicts`: that table is six columns with a field-by-field
    payload diff and four resolution forms per row, and it was the single largest thing
    on a page whose complaint was length. It is linked from the work queue, which is
    where somebody looking for it actually is.

    Nothing was deleted. Every fact, control and explanation still has a home -- what
    changed is WHEN it renders: once instead of twice, on demand instead of always, and
    next to the thing it describes.
    """
    school = getattr(request, "school", None)
    if not school:
        return redirect_staff_without_school(
            request,
            message="Select your school to view sync status.",
        )
    pref_url = reverse("siteconfig:user_preferences")
    # include_coverage: the week strip is the one expensive field in the schedule
    # summary, so the PAGE asks for it and the status poll does not.
    panel = _edge_sync_panel_context(school, include_coverage=True)
    ctx = {
        "pairing_requests": _pending_pairing_requests(school),
        "school": school,
        "sync_available": False,
        "action_url": pref_url,
        "action_text": _("Back to preferences"),
        "sync_stats_total": 0,
        "sync_stats_pending": 0,
        "conflict_groups": [],
        "conflicts_url": _safe_sync_reverse("siteconfig:sync_conflicts"),
        "scheduled_hub_url": _safe_sync_reverse(
            "siteconfig:scheduled_reports_delivery_hub"
        ),
        "console_url": _safe_sync_reverse("siteconfig:console_domains_hub"),
        "admin_sync_conflict_url": None,
        "oldest_conflict_at": None,
        # LAST, so the panel wins every key it owns. Dropping this spread is not a
        # subtle failure: `edge_sync_enabled` becomes undefined, the template reads it as
        # falsy, and a BOX silently renders the cloud-side controls -- offering "Queue
        # full resync" to a deployment that can call out perfectly well, while the
        # strings island renders empty and the week strip never draws.
        **panel,
    }
    try:
        from .models import SyncConflict
    except ImportError:
        return render(request, "siteconfig/sync_center.html", ctx)

    stats = SyncConflict.objects.filter(school=school).aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=SyncConflict.Status.PENDING)),
    )
    # The work queue needs the SHAPE of the backlog, not the rows: "2 Attendance, 1
    # Student" is what tells an operator whether this is one bad import or a systemic
    # disagreement, and it is three integers rather than a page of records.
    pending = SyncConflict.objects.filter(
        school=school, status=SyncConflict.Status.PENDING
    )
    groups = list(
        pending.values("entity_type")
        .annotate(pending_count=Count("id"))
        .order_by("-pending_count", "entity_type")[:_WORK_QUEUE_GROUP_LIMIT]
    )
    oldest = (
        pending.order_by("created_at").values_list("created_at", flat=True).first()
    )
    ctx.update(
        {
            "sync_available": True,
            "sync_stats_total": stats.get("total") or 0,
            "sync_stats_pending": stats.get("pending") or 0,
            "conflict_groups": groups,
            "oldest_conflict_at": oldest,
        }
    )
    return render(request, "siteconfig/sync_center.html", ctx)


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET"])
def sync_conflicts(request):
    """The conflict queue, on its own page.

    IT LIVES HERE RATHER THAN ON THE SYNC CENTER because of what it needs: six columns, a
    field-by-field comparison of the two versions of every record, and four resolution
    forms per row. Folded into a status page it was both the longest section and the most
    cramped one -- the diff that decides which version of a grade survives was rendering
    inside a collapsed row of a table inside a card. Given a page, the comparison gets the
    width it needs and the Sync Center gets to be short.
    """
    school = getattr(request, "school", None)
    if not school:
        return redirect_staff_without_school(
            request,
            message="Select your school to view sync conflicts.",
        )
    back_url = _safe_sync_reverse("siteconfig:sync_center")
    empty_ctx = {
        "school": school,
        "conflicts": [],
        "page_obj": None,
        "sync_available": False,
        "sync_center_url": back_url,
        "action_url": back_url,
        "action_text": _("Back to Sync Center"),
        "sync_stats_total": 0,
        "sync_stats_pending": 0,
        "conflict_status_filter": "pending",
        "conflict_entity_filter": "",
        "conflict_groups": [],
        "bulk_actions": _conflict_bulk_actions(),
        "bulk_url": _safe_sync_reverse("siteconfig:sync_center_bulk_resolve"),
        "admin_sync_conflict_url": None,
        "pagination_extra_query": "",
    }
    try:
        from .models import SyncConflict
    except ImportError:
        return render(request, "siteconfig/sync_conflicts.html", empty_ctx)
    stats = SyncConflict.objects.filter(school=school).aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=SyncConflict.Status.PENDING)),
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
    # template because the template cannot call a function with arguments -- and a button
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
        except Exception:  # noqa: BLE001 -- a display aid must never break the page
            _logger.debug("could not build the conflict comparison", exc_info=True)
            _c.field_rows = []
            _c.may_keep_client, _c.keep_client_refusal = True, ""
    return render(
        request,
        "siteconfig/sync_conflicts.html",
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


def _pending_pairing_requests(school):
    """Boxes waiting to be adopted by THIS school. Never breaks the page."""
    try:
        from apps.sync_engine.pairing_service import pending_requests_for_school

        return list(pending_requests_for_school(school)[:20])
    except Exception:  # noqa: BLE001 — an empty panel beats a 500 on the conflicts page
        _logger.debug("could not load pending pairing requests", exc_info=True)
        return []


@login_required
@permission_required("settings.manage")
@require_http_methods(["POST"])
def sync_center_pair_approve(request):
    """Adopt a box. THE authorization decision in the whole pairing protocol.

    Deliberately a plain authenticated POST on the tenant host: the point of the
    box->cloud direction is that approving happens inside a session that already
    proved who the admin is, against the school they are already signed in to.
    ``approve_pairing`` re-checks both — that the code belongs to this tenant, and
    that this user administers it — so a stolen code is worth nothing on its own.
    """
    school = getattr(request, "school", None)
    code = (request.POST.get("user_code") or "").strip()
    if not school:
        return redirect_staff_without_school(
            request, message="Select your school to approve a box."
        )
    from apps.sync_engine.pairing_service import approve_pairing

    result = approve_pairing(code=code, approver=request.user, school=school)
    if result.get("ok"):
        messages.success(
            request,
            _("Box approved. It will finish pairing within a few seconds."),
        )
    else:
        messages.error(request, _pairing_error_message(result))
    return redirect(f"{reverse('siteconfig:sync_center')}#pairing")


@login_required
@permission_required("settings.manage")
@require_http_methods(["POST"])
def sync_center_pair_deny(request):
    """Refuse a box. Terminal — it is told, and stops asking."""
    school = getattr(request, "school", None)
    code = (request.POST.get("user_code") or "").strip()
    if not school:
        return redirect_staff_without_school(
            request, message="Select your school to manage box pairing."
        )
    from apps.sync_engine.pairing_service import deny_pairing

    result = deny_pairing(
        code=code,
        approver=request.user,
        school=school,
        reason=(request.POST.get("reason") or "").strip(),
    )
    if result.get("ok"):
        messages.success(request, _("Pairing request denied."))
    else:
        messages.error(request, _pairing_error_message(result))
    return redirect(f"{reverse('siteconfig:sync_center')}#pairing")


def _pairing_error_message(result: dict) -> str:
    """Say what went wrong in words an administrator can act on."""
    error = result.get("error") or ""
    if error == "unknown_code":
        return _("That pairing code does not match any request. Check the box's screen.")
    if error == "expired":
        return _("That request has expired. Start pairing again on the box.")
    if error == "wrong_tenant":
        return _("That code belongs to a different school.")
    if error == "forbidden":
        return _("You do not have permission to approve a box for this school.")
    if error == "unknown_school":
        return _(
            "That box asked for a school this cloud does not recognise. Check the "
            "slug configured on the box."
        )
    if error.startswith("not_pending"):
        return _("That request has already been handled.")
    return _("The pairing request could not be updated.")


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
        return redirect("siteconfig:sync_conflicts")
    conflict = get_object_or_404(SyncConflict, pk=conflict_id, school=school)
    if conflict.status != SyncConflict.Status.PENDING:
        messages.info(request, "Conflict already resolved.")
        return redirect("siteconfig:sync_conflicts")
    resolution_str = (request.POST.get("resolution") or "").strip().lower()
    # WHY, captured with the decision. resolution_note is the audit trail alongside
    # resolved_by/resolved_at, and a resolution nobody can explain later is not a
    # resolution — especially on a money or grade record.
    note = (request.POST.get("note") or "").strip()[:255]
    ok, reason = apply_resolution(conflict, resolution_str, request.user, note=note)
    if not ok:
        messages.error(request, reason or _("Invalid resolution."))
        return redirect("siteconfig:sync_conflicts")
    messages.success(
        request,
        _("Conflict resolved (%(resolution)s).") % {"resolution": resolution_str},
    )
    return redirect("siteconfig:sync_conflicts")


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
        # --- the verdict line. One sentence, one place. -----------------------------
        "verdict_ok": gettext("Syncing normally"),
        "verdict_failed": gettext("Last sync failed"),
        "verdict_running": gettext("Syncing now"),
        "verdict_queued": gettext("Sync queued"),
        "verdict_idle": gettext("No sync has run yet"),
        "verdict_cloud": gettext("Waiting for the box to call in"),
        "verdict_last": gettext("Last synced"),
        "verdict_never": gettext("Never synced"),
        # The two "next" answers are DIFFERENT QUESTIONS and used to be rendered as if
        # they were the same one, in two cards, with no way to tell them apart.
        "verdict_next_rule": gettext("next scheduled"),
        "verdict_next_cadence": gettext("next check"),
        "cycles_word": gettext("cycles in"),
        "cycles_last_day": gettext("the last day"),
        "unit_days": gettext("days"),
        "cycles_failed": gettext("failed"),
        # --- the sparkline ----------------------------------------------------------
        "spark_caption": gettext("Cycles per hour, oldest on the left."),
        "spark_hours": gettext("hours"),
        "spark_failed_hours": gettext("hour(s) had a failure."),
        "spark_quiet_hours": gettext("hour(s) with no cycle at all."),
        # --- the activity timeline --------------------------------------------------
        "timeline_synced": gettext("Synced"),
        "timeline_failed": gettext("Failed"),
        "timeline_records": gettext("records"),
        "timeline_up": gettext("up"),
        "timeline_down": gettext("down"),
        "timeline_empty": gettext(
            "No cycle has run yet. Once one does, each appears here with what it carried "
            "and how long it took."
        ),
        # --- the week strip ---------------------------------------------------------
        "strip_sync": gettext("sync"),
        "strip_syncs": gettext("syncs"),
        "strip_first_at": gettext("first at"),
        "strip_no_sync": gettext("no scheduled sync. The check-in floor still applies."),
        "strip_in_gap": gettext(
            "inside the longest gap. Only the check-in floor covers this hour."
        ),
        "next_none": gettext("Nothing scheduled"),
        "next_floor_only": gettext("check-in floor only"),
        "coverage_per_week": gettext("syncs a week"),
        "coverage_longest_gap": gettext("longest gap"),
        "coverage_unbounded": gettext("No rule fires — the adaptive cadence is in charge."),
        "coverage_flagged": gettext(
            "That is longer than this schedule's own threshold — worth a look."
        ),
        "coverage_clear": gettext("No gap longer than this schedule's threshold."),
        "unit_min": gettext("min"),
        "policy_unsaved": gettext("Not saved yet"),
        "policy_saving": gettext("Saving…"),
        "probe_done": gettext("Done."),
        "probe_failed": gettext("Could not reach the cloud from here."),
    }


def _edge_sync_panel_context(school, *, include_coverage=False):
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

    from apps.sync_engine.edge_enabled import edge_sync_enabled

    ctx = {
        # Resolved, not the raw env flag: a paired box IS an edge box, and a panel
        # that said otherwise while the box was happily syncing would be lying.
        "edge_sync_enabled": edge_sync_enabled(),
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
        from apps.sync_engine.schedule import describe_rule, dst_note_for_rule

        rows = list(SyncSchedule.objects.filter(school=school))
        tz = schedule_policy.school_timezone(school)
        moment = dj_timezone_now()
        for row in rows:
            rule = row.to_rule()
            row.human = describe_rule(rule)
            row.form = SyncScheduleForm(instance=row)
            # The clock-change note belongs to the rule whose time is actually affected,
            # not to the page. Empty for every other rule and for the other fifty-one
            # weeks of the year.
            row.dst_note = dst_note_for_rule(rule, tz, after=moment)
        ctx["sync_schedule_rules"] = rows
        ctx["sync_schedule_new_form"] = SyncScheduleForm(instance=SyncSchedule(school=school))
        ctx["sync_schedule_summary"] = schedule_policy.schedule_summary(
            school, include_coverage=include_coverage
        )
        ctx["sync_schedule_save_url"] = _safe_sync_reverse("siteconfig:sync_schedule_save")
        ctx["sync_schedule_preview_url"] = _safe_sync_reverse(
            "siteconfig:sync_schedule_preview"
        )
        ctx["sync_schedule_hour_labels"] = _STRIP_HOUR_LABELS
    except Exception:  # noqa: BLE001 — an unmigrated box must still render the page
        _logger.debug("sync schedule panel context failed", exc_info=True)
        ctx["sync_schedule_rules"] = []
        ctx["sync_schedule_new_form"] = None
        ctx["sync_schedule_summary"] = None
        ctx["sync_schedule_save_url"] = None
        ctx["sync_schedule_preview_url"] = None
        ctx["sync_schedule_hour_labels"] = _STRIP_HOUR_LABELS

    # The policy AROUND the rules. Separate try block on purpose: a tenant whose schedule
    # rules fail to load should still be able to see and change the check-in ceiling,
    # because that is the setting that decides whether support can reach the box at all.
    try:
        from apps.siteconfig.forms_sync_policy import SyncPolicyForm
        from apps.sync_engine.models_policy import SyncPolicy

        row = SyncPolicy.objects.filter(school=school).first()
        ctx["sync_policy_form"] = SyncPolicyForm(
            instance=row or SyncPolicy(school=school)
        )
        ctx["sync_policy_save_url"] = _safe_sync_reverse("siteconfig:sync_policy_save")
    except Exception:  # noqa: BLE001
        _logger.debug("sync policy panel context failed", exc_info=True)
        ctx["sync_policy_form"] = None
        ctx["sync_policy_save_url"] = None
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
    # DELIBERATELY the raw env flag, not the resolved edge_sync_enabled(). This is an
    # authorization bypass ("on a box, let the box's own screens probe without a tenant
    # permission"), not a question about whether sync runs. Widening it on the strength
    # of a database row would let a pairing quietly change who may call this. A paired
    # box without the flag simply asks for settings.manage, which its admins hold.
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
    return redirect("siteconfig:sync_conflicts")


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

    from apps.sync_engine import sync_runner

    # Refuse BEFORE recording anything on a deployment that cannot perform this action.
    # The box-initiated cycle is meaningless on the cloud (there is no operator for the
    # cloud to call out to, and it cannot reach into the box's LAN), so running it here
    # only manufactured a red run row on every click. Point the operator at the control
    # that does work from this side.
    from apps.sync_engine.edge_enabled import edge_sync_enabled as _edge_sync_enabled

    if not _edge_sync_enabled():
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
        # 409, NOT 403. No tenant bound to the request is a STATE problem, not an
        # authorization one: the caller may be perfectly entitled and simply be on a
        # host that resolves no school. The permission check a few lines below returns
        # a real 403, and collapsing both into 403 leaves the polling panel unable to
        # tell "you may not see this" from "there is nothing here to see" -- different
        # problems with different fixes for the operator. This WAS 409 until 852b3990a
        # (a 139-file land) changed it in passing along with the payload key;
        # test_no_school_in_context_is_a_409_not_a_crash exists to pin it.
        return JsonResponse({"ok": False, "error": "No school"}, status=409)

    # DELIBERATELY the raw env flag, not the resolved edge_sync_enabled(). This is an
    # authorization bypass ("on a box, let the box's own screens probe without a tenant
    # permission"), not a question about whether sync runs. Widening it on the strength
    # of a database row would let a pairing quietly change who may call this. A paired
    # box without the flag simply asks for settings.manage, which its admins hold.
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

    # The requested window, clamped to the offered set. An unknown value is the default
    # rather than an error: this is an observability read, and a panel that 400s because
    # somebody hand-edited a query string is a panel that looks like broken sync.
    window_key = (request.GET.get("window") or "24h").strip().lower()
    if window_key not in _STATUS_WINDOW_CHOICES:
        window_key = "24h"
    window_hours = _STATUS_WINDOW_CHOICES[window_key]

    now = timezone.now()
    payload.update({
        "ok": True,
        "window": window_key,
        "generated_at": now.isoformat(),
        "edge_sync_enabled": edge_enabled,
        "link": None,
        "cadence": None,
        "latest_run": None,
        "recent_runs": [],
        "recent_records": [],
        "totals": {},
        "history": [],
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

        window_start = now - timedelta(hours=window_hours)
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
        # One count per hour across the window, so the panel can draw a shape instead
        # of a number. "44 cycles, 2 failed" cannot tell a box that has been steady all
        # day from one that did 44 cycles in ten minutes and then went silent -- and
        # that difference is the entire question an operator opens this page to ask.
        payload["history"] = _hourly_history(window, now=now, hours=window_hours)
        payload["totals"] = {
            "window_hours": window_hours,
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


def _hourly_history(window_qs, *, now, hours=_STATUS_WINDOW_HOURS) -> list:
    """Cycles per hour over the status window, oldest first, gaps filled with zeros.

    ZEROS ARE THE POINT. Returning only the hours that HAVE runs would draw a continuous
    healthy line over a box that was off all night -- the sparkline would compress the
    silence out of existence. Every hour in the window gets a slot whether or not
    anything happened in it.
    """
    from django.db.models.functions import TruncHour
    from django.utils import timezone as dj_tz

    buckets = {}
    try:
        rows = (
            window_qs.annotate(hour=TruncHour("created_at"))
            .values("hour")
            .annotate(runs=Count("id"), failed=Count("id", filter=Q(ok=False)))
            .order_by("hour")
        )
        for row in rows:
            hour = row["hour"]
            if hour is None:
                continue
            buckets[hour.replace(minute=0, second=0, microsecond=0)] = (
                row["runs"] or 0,
                row["failed"] or 0,
            )
    except Exception:  # noqa: BLE001 -- a sparkline must never break the status poll
        _logger.debug("hourly history failed", exc_info=True)
        return []

    local_now = dj_tz.localtime(now)
    top_of_hour = local_now.replace(minute=0, second=0, microsecond=0)
    out = []
    for back in range(hours - 1, -1, -1):
        slot = top_of_hour - timedelta(hours=back)
        runs, failed = buckets.get(slot, (0, 0))
        out.append({"at": slot.isoformat(), "runs": runs, "failed": failed})
    return out


@login_required
@permission_required("settings.manage")
@require_http_methods(["POST"])
def sync_schedule_preview(request):
    """Cost a CANDIDATE schedule without saving it, and return the week strip.

    THIS ENDPOINT IS WHY THE STRIP IS TRUSTWORTHY. The obvious implementation of a live
    preview is to re-derive occurrences in JavaScript as the operator types. That would
    put a second scheduler in the browser, and the two would drift the first time either
    changed -- silently, because a wrong strip still looks like a strip. So the browser
    computes NOTHING: it posts the rule set currently in the editor, and this runs the
    same ``apps.sync_engine.schedule`` functions the box itself obeys.

    Read-only in every path. It builds unsaved model instances to validate them and
    never calls ``save()``, so a preview cannot retime anybody's box.

    Accepts:
      * the ``SyncScheduleForm`` fields for the rule being edited or added (optional);
      * ``rule_id`` -- the saved rule that candidate REPLACES, excluded from the set;
      * ``paused_ids`` -- saved rules to treat as switched off, for the toggle preview.
    """
    school = getattr(request, "school", None)
    if not school:
        return JsonResponse({"ok": False, "error": "No school"}, status=403)

    from apps.siteconfig.forms_sync_schedule import SyncScheduleForm
    from apps.sync_engine import schedule_policy
    from apps.sync_engine.models_schedule import SyncSchedule
    from apps.sync_engine.schedule import describe

    rule_id = (request.POST.get("rule_id") or "").strip()
    paused = {
        int(value)
        for value in (request.POST.get("paused_ids") or "").split(",")
        if value.strip().isdigit()
    }

    saved = list(SyncSchedule.objects.filter(school=school, is_enabled=True))
    rules = [
        row.to_rule()
        for row in saved
        if row.pk not in paused and str(row.pk) != rule_id
    ]

    errors = {}
    candidate_valid = None
    # A candidate is only in play when the editor actually sent one. An empty POST is the
    # toggle case: preview what is saved, minus whatever is paused.
    if any(key in request.POST for key in ("mode", "interval_minutes", "at_times")):
        instance = None
        if rule_id.isdigit():
            instance = SyncSchedule.objects.filter(
                pk=int(rule_id), school=school
            ).first()
        form = SyncScheduleForm(
            request.POST, instance=instance or SyncSchedule(school=school)
        )
        candidate_valid = form.is_valid()
        if candidate_valid:
            unsaved = form.save(commit=False)
            unsaved.school = school
            if unsaved.is_enabled:
                rules.append(unsaved.to_rule())
        else:
            errors = {
                field: [str(message) for message in messages_]
                for field, messages_ in form.errors.items()
            }

    now = dj_timezone_now()
    return JsonResponse(
        {
            "ok": True,
            "valid": candidate_valid,
            "errors": errors,
            "description": describe(rules),
            "rule_labels": [rule.label for rule in rules],
            # next_runs rides inside coverage rather than beside it, so the strip and the
            # list next to it are guaranteed to describe the same rule set.
            "coverage": schedule_policy.coverage_for(school, now=now, rules=rules),
        }
    )


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


@login_required
@permission_required("settings.manage")
@require_http_methods(["POST"])
def sync_policy_save(request):
    """Save the check-in ceiling and catch-up preference for ``request.school``.

    School from the REQUEST, never from POST, for the same reason as
    :func:`sync_schedule_save`: these values decide when a box talks to the cloud, and
    accepting a school id from the form would let anyone reaching this endpoint retime
    another tenant's box.

    ``update_or_create`` on the school rather than a pk from the form: this row is a
    singleton per school, so there is no id for a caller to supply and none to forge.
    """
    school = getattr(request, "school", None)
    if not school:
        return redirect_staff_without_school(
            request, message=_("Select your school to change sync settings.")
        )

    from apps.siteconfig.forms_sync_policy import SyncPolicyForm
    from apps.sync_engine.models_policy import SyncPolicy

    back = _safe_sync_reverse("siteconfig:sync_center") or "/"
    instance = SyncPolicy.objects.filter(school=school).first() or SyncPolicy(school=school)
    form = SyncPolicyForm(request.POST, instance=instance)
    if not form.is_valid():
        for field, errors in form.errors.items():
            label = form.fields[field].label if field in form.fields else ""
            for error in errors:
                messages.error(request, f"{label}: {error}" if label else str(error))
        return redirect(back)

    policy = form.save(commit=False)
    policy.school = school
    policy.save()
    _wake_for_schedule_change(school)
    messages.success(
        request,
        _(
            "Sync settings saved. They take effect on the box at its next sync — the "
            "cloud cannot contact a box directly."
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
