"""G6: a long-poll changes feed, so cloud->box stops being poll-bound.

THE GAP. The appliance is behind NAT, so the cloud can never open a connection to it.
Every transfer is box-initiated, which means a change made on the cloud waits out the
box's cadence before it is even offered - up to ``RMC_EDGE_SYNC_INTERVAL_SECONDS``, and
the adaptive cadence deliberately BACKS OFF when a box looks idle, so a quiet school can
sit minutes behind. For a bursar issuing a receipt while a parent waits at the desk, that
is the difference between a working system and one people stop trusting.

THE PATTERN. CouchDB's ``_changes`` feed: the client holds one ordinary HTTP request open
and the server answers the moment something changes, or returns "nothing" when the hold
expires. It needs no persistent socket, no inbound port on the box, and no websocket
infrastructure - it traverses NAT and corporate proxies because it is just a slow GET.
Cloud->box collapses from a cadence interval to roughly one second.

IT IS A LATENCY OPTIMISATION, NOT A TRANSPORT. This endpoint never returns data. It
answers one question - "is there anything for me?" - and the box then runs its ordinary,
fully-tested sync cycle. So every guarantee about cursors, conflict policy, referential
integrity and replay defence is untouched by it, and killing the feed mid-flight
degrades to exactly the cadence behaviour that exists today with no lost rows.

COST CONTROL. Answering "is there anything?" from the database would mean an existence
query per synced entity - fifteen - once a second per connected box, which is a bigger
load problem than the polling it replaces. The primary answer therefore comes from an
in-memory beacon (``apps.sync_engine.change_beacon``), with a periodic database sweep as
the safety net for deployments whose cache is per-process. See that module for why the
net is required rather than optional.
"""
from __future__ import annotations

import time

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.edge_auth import EdgeCredentialAuthentication
from apps.schools.tenant_api_guards import user_may_operate_on_school

# Defaults. The hold is deliberately shorter than the 30s default timeout on the box's
# own HTTP client and well inside the idle timeout of every common proxy and load
# balancer, so an expiring hold is a clean 200 rather than a connection reset the box has
# to distinguish from being offline.
_DEFAULT_MAX_WAIT_SECONDS = 25
_DEFAULT_POLL_STEP_SECONDS = 1.0
_DEFAULT_DB_SWEEP_SECONDS = 5.0


def _setting(name, default):
    try:
        return type(default)(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def changes_feed_enabled() -> bool:
    return bool(getattr(settings, "RMC_SYNC_CHANGES_FEED_ENABLED", True))


def _database_has_changes(school, since) -> bool:
    """The safety net: ask the database directly. ``since`` may be ``None`` (= anything).

    Costs one cheap EXISTS per synced entity plus one for tombstones, which is why it
    runs on an interval rather than on every loop iteration.
    """
    from apps.api.sync_services import _get_entity_config
    from apps.sync_engine.models import SyncTombstone

    for _entity, (model, _fields) in _get_entity_config(include_derived=True).items():
        qs = model._default_manager.filter(school=school)  # school= is the tenant-isolation kwarg
        if since is not None:
            qs = qs.filter(updated_at__gt=since)
        try:
            if qs.exists():
                return True
        except Exception:  # noqa: BLE001 - a model without updated_at must not break the feed
            continue
    try:
        tombs = SyncTombstone.objects.filter(school=school)
        if since is not None:
            tombs = tombs.filter(deleted_at__gt=since)
        # A DELETION is a change. Omitting tombstones here would make the feed answer
        # "nothing new" for the one kind of change an operator most needs propagated fast.
        if tombs.exists():
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


@extend_schema_view(
    get=extend_schema(
        tags=["Offline Sync"],
        summary="Long-poll: is there anything new for this box?",
        description=(
            "Holds the request open for up to `wait` seconds and answers the moment the "
            "school has a change newer than `since`. Returns `{changed, high_water, "
            "waited_seconds}` and never any row data — the box then runs its ordinary "
            "sync cycle. Collapses cloud->box latency from the polling interval to about "
            "a second, over plain HTTP, through NAT."
        ),
        responses={200: dict, 403: dict},
    ),
)
class SyncChangesFeedView(APIView):
    """The box asks; the cloud answers as soon as it can, or says "nothing" politely."""

    authentication_classes = [EdgeCredentialAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school = getattr(request, "school", None)
        if school is None:
            return Response({"ok": False, "error": "school_required"}, status=403)
        if not user_may_operate_on_school(request, school):
            return Response({"ok": False, "error": "forbidden"}, status=403)
        if not changes_feed_enabled():
            # Answer immediately and truthfully rather than 404: the box treats
            # `supported: false` as "fall back to the cadence", which is a working
            # deployment, not an error.
            return Response({"ok": True, "supported": False, "changed": True, "waited_seconds": 0})

        raw_since = (request.query_params.get("since") or "").strip()
        since = parse_datetime(raw_since) if raw_since else None
        if raw_since and since is None:
            return Response(
                {"ok": False, "error": "invalid_since", "detail": "use ISO-8601"}, status=400
            )
        if since is not None and timezone.is_naive(since):
            since = timezone.make_aware(since, timezone.get_current_timezone())

        max_wait = _setting("RMC_SYNC_CHANGES_FEED_MAX_WAIT_SECONDS", _DEFAULT_MAX_WAIT_SECONDS)
        try:
            wait = min(max(0, int(request.query_params.get("wait") or max_wait)), max_wait)
        except (TypeError, ValueError):
            wait = max_wait
        step = _setting("RMC_SYNC_CHANGES_FEED_POLL_STEP_SECONDS", _DEFAULT_POLL_STEP_SECONDS)
        sweep_every = _setting("RMC_SYNC_CHANGES_FEED_DB_SWEEP_SECONDS", _DEFAULT_DB_SWEEP_SECONDS)

        from apps.sync_engine.change_beacon import last_change

        since_epoch = since.timestamp() if since is not None else None
        started = time.monotonic()
        # The first answer is always from the database. Entering the hold on the strength
        # of a cache miss would make an idle beacon look like "no changes" and delay a
        # change that is already sitting there.
        if _database_has_changes(school, since):
            return self._answer(True, school, started)

        last_sweep = time.monotonic()
        while (time.monotonic() - started) < wait:
            time.sleep(min(step, max(0.0, wait - (time.monotonic() - started))))
            beacon = last_change(getattr(school, "pk", None))
            if beacon is not None and (since_epoch is None or beacon > since_epoch):
                # Confirm against the database before answering: the beacon is a hint that
                # SOMETHING was written, and a write the box itself just pushed up would
                # otherwise wake it for its own echo, once per cycle, forever.
                if _database_has_changes(school, since):
                    return self._answer(True, school, started)
            if (time.monotonic() - last_sweep) >= sweep_every:
                last_sweep = time.monotonic()
                if _database_has_changes(school, since):
                    return self._answer(True, school, started)
        return self._answer(False, school, started)

    @staticmethod
    def _answer(changed, school, started):
        return Response(
            {
                "ok": True,
                "supported": True,
                "changed": bool(changed),
                "waited_seconds": round(time.monotonic() - started, 2),
                "server_time": timezone.now().isoformat(),
            }
        )


__all__ = ["SyncChangesFeedView", "changes_feed_enabled"]
