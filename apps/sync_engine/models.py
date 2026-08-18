"""Sync-engine models.

Most sync domain logic lives in services.py; offline queue rows use
apps.api.mobile_api.OfflineSyncQueue. The one persistent model here is the
echo-suppression ledger that makes edge<->cloud sync BIDIRECTIONAL without an
infinite ping-pong of sync-applied rows.
"""
from __future__ import annotations

from django.db import models

# Sentinel so ``None`` (a genuinely null updated_at) is distinguishable from
# "no ledger entry for this row" when suppressing echoes.
_MISSING = object()


class SyncApplyLedger(models.Model):
    """Provenance marker for echo-suppression in bidirectional edge<->cloud sync.

    THE ECHO PROBLEM. Applying a pulled/pushed row calls ``.save()``, which bumps
    ``updated_at`` (auto_now) to *now*. The delta builder selects rows by
    ``updated_at__gt=cursor``, so the freshly-applied row is immediately re-selected
    and shipped straight back to the origin — forever. Data still converges, but the
    churn burns bandwidth and can mask real conflicts.

    THE FIX. When ``apply_changes`` / ``apply_edge_inserts`` writes a row as part of
    SYNC (not a local user edit), it upserts a ledger row recording that row's
    ``updated_at`` AFTER the write. ``build_edge_delta_bundle`` then EXCLUDES any
    candidate whose current ``updated_at`` still equals ``applied_updated_at`` — i.e.
    the row is unchanged since sync wrote it, so re-sending it would be a pure echo.
    A later LOCAL edit bumps ``updated_at`` away from the recorded value, so the row
    no longer matches the ledger and DOES propagate. Provenance, not a clock compare —
    so it is immune to box/cloud clock skew.

    TENANCY. A SHARED/public-schema table discriminated by the ``school`` FK, exactly
    like ``siteconfig.SyncConflict`` — one physical table, rows scoped per tenant. On
    the single-tenant edge box there is only ever one school's rows here anyway.
    """

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="sync_apply_ledger"
    )
    entity_type = models.CharField(max_length=64)
    # str(pk): entity primary keys are int (most) or uuid — a char column holds both
    # and compares cleanly regardless of the row's pk type.
    local_pk = models.CharField(max_length=64)
    # The row's updated_at immediately after the sync write. Nullable because a synced
    # model need not have an updated_at (then echo-suppression simply never fires for it).
    applied_updated_at = models.DateTimeField(null=True, blank=True)
    # "cloud-pull" | "edge-push" — which direction wrote this. Observability only; the
    # suppression logic does not depend on it.
    origin = models.CharField(max_length=32, default="", blank=True)
    applied_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "sync_engine"
        verbose_name = "Sync apply ledger entry"
        verbose_name_plural = "Sync apply ledger"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "entity_type", "local_pk"],
                name="uq_syncapplyledger_row",
            )
        ]
        indexes = [models.Index(fields=["school", "entity_type"])]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"{self.entity_type}:{self.local_pk}@{self.applied_updated_at}"


class EdgeSyncRun(models.Model):
    """One row per edge<->cloud sync CYCLE, so the Sync Center can show the latest outcome.

    The observability companion to :class:`SyncApplyLedger`. The self-healing
    :func:`apps.sync_engine.sync_runner.run_sync_cycle` records EXACTLY ONE of these per
    cycle it drives — INCLUDING cycles that ran with the edge flag off, hit an unreachable
    operator, or were rejected — so a "Sync now" click surfaces as a visible ok/fail row
    instead of a crashed tenant page. This table is observability only; it changes no
    conflict/money policy and money stays cloud-authoritative.

    TENANCY mirrors ``SyncApplyLedger`` — a SHARED/public-schema table discriminated by the
    ``school`` FK. On the single-tenant edge box there is only ever one school's rows here.
    """

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="edge_sync_runs"
    )
    # "dry" (pull-only, never posts local changes up) | "live" (push then pull).
    mode = models.CharField(max_length=8, default="live")
    pushed = models.IntegerField(default=0)
    pulled = models.IntegerField(default=0)
    conflicts = models.IntegerField(default=0)
    created = models.IntegerField(default=0)
    upserted = models.IntegerField(default=0)
    ok = models.BooleanField(default=False)
    message = models.TextField(blank=True, default="")
    error = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "sync_engine"
        ordering = ["-created_at"]
        verbose_name = "Edge sync run"
        verbose_name_plural = "Edge sync runs"
        indexes = [models.Index(fields=["school", "-created_at"])]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"EdgeSyncRun({self.mode},{'ok' if self.ok else 'fail'})#{self.pk}"

    @classmethod
    def record(cls, school, **kw):
        """Create one summarizing run row for ``school``.

        Self-healing: stray keys (e.g. the runner's whole result dict, which carries
        ``enabled``/``mode``) are dropped rather than raised on, so the caller can hand
        over its result without shape-coupling to this model.
        """
        valid = {f.name for f in cls._meta.concrete_fields}
        clean = {k: v for k, v in kw.items() if k in valid and k != "school"}
        return cls.objects.create(school=school, **clean)

    @classmethod
    def latest_for(cls, school):
        """The most recent run for ``school`` (``Meta.ordering`` is newest-first), or None."""
        if school is None:
            return None
        return cls.objects.filter(school=school).first()


class EdgeSyncCursor(models.Model):
    """Durable per-direction high-water mark for the edge<->cloud sync RUNNER.

    The ``post_edge_outbox`` / ``pull_edge_inbox`` COMMANDS keep their cursors in files
    the operator passes on the command line. The runner — which is what both the "Sync
    now" button and every automatic trigger actually call — had no cursor at all: it
    passed ``since=None`` in both directions and threw away the ``X-RMC-Sync-High-Water``
    header the download endpoint already returns. So every 180s tick re-scanned and
    re-shipped the school's ENTIRE corpus, and a backlog could never be recorded as
    drained. This table gives the runner the same durable position, in the DB, where a
    UI-driven and a scheduler-driven run can share it.

    ADVANCE ONLY ON SUCCESS. A cursor moves after the work it covers is confirmed
    applied; a rejected page or an unreachable operator leaves it exactly where it was,
    so the next cycle re-sends. The apply path is idempotent (update-by-pk, upsert-by
    ``(school, client_offline_id)``), so a re-send is safe and a lost row is not.

    TENANCY mirrors :class:`SyncApplyLedger` — one SHARED/public-schema table
    discriminated by the ``school`` FK.
    """

    PUSH = "push"
    PULL = "pull"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="edge_sync_cursors"
    )
    # "push" (box -> cloud) | "pull" (cloud -> box). The two directions advance
    # independently: a failing push must never hold back a working pull.
    direction = models.CharField(max_length=8)
    # NULL means "no position yet" — ask for everything. That is also exactly what a
    # full-resync request restores, which is why reset is a nulling, not a deletion.
    high_water = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "sync_engine"
        verbose_name = "Edge sync cursor"
        verbose_name_plural = "Edge sync cursors"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "direction"], name="uq_edgesynccursor_school_direction"
            )
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"EdgeSyncCursor({self.direction}@{self.high_water})"


class EdgeSyncDirective(models.Model):
    """A cloud-authored instruction the BOX collects on its next poll.

    Why this exists at all: an edge box sits on a private LAN behind NAT, so the cloud
    can never open a connection TO it. Every transfer is box-initiated. A cloud operator
    pressing a "sync the box now" button is therefore asking for something physically
    impossible — which is exactly why that button failed every single time it was
    pressed. The honest mechanism is the reverse: the cloud RECORDS what it wants, and
    the box picks it up the next time it calls out (which it does at least every
    ``RMC_EDGE_SYNC_INTERVAL_SECONDS``, default 180s).

    Delivery is observable rather than acknowledged. ``served_at`` is stamped when the
    download endpoint hands the directive to the box, so the operator can tell "requested
    but the box has not called home yet" (a connectivity problem) from "delivered"
    (the box has it). There is deliberately no ack protocol: a box that never returns is
    a box that is off or offline, and inventing an ack would not change that.
    """

    FULL_RESYNC = "full-resync"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="edge_sync_directives"
    )
    kind = models.CharField(max_length=32, default=FULL_RESYNC)
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    # Null until the box actually collects it. One-shot: a served directive is never
    # re-served, so a resync cannot be triggered repeatedly by one request.
    served_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "sync_engine"
        ordering = ["-requested_at"]
        verbose_name = "Edge sync directive"
        verbose_name_plural = "Edge sync directives"
        indexes = [models.Index(fields=["school", "served_at"])]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"EdgeSyncDirective({self.kind},{'served' if self.served_at else 'pending'})"


def request_full_resync(school, user=None):
    """Queue a full-resync directive for ``school``, collapsing duplicates.

    Idempotent on purpose: an operator clicking twice while the box is offline should not
    queue two resyncs. Returns the pending directive.
    """
    pending = EdgeSyncDirective.objects.filter(
        school=school, kind=EdgeSyncDirective.FULL_RESYNC, served_at__isnull=True
    ).first()
    if pending is not None:
        return pending
    return EdgeSyncDirective.objects.create(
        school=school,
        kind=EdgeSyncDirective.FULL_RESYNC,
        requested_by=user if getattr(user, "pk", None) else None,
    )


def claim_pending_directive(school):
    """Hand the box its oldest un-served directive and mark it served, or ``None``.

    Called by the download endpoint while it is already serving the box, so the
    directive rides an existing round trip rather than needing a channel of its own.
    """
    from django.utils import timezone as _tz

    directive = (
        EdgeSyncDirective.objects.filter(school=school, served_at__isnull=True)
        .order_by("requested_at")
        .first()
    )
    if directive is None:
        return None
    directive.served_at = _tz.now()
    directive.save(update_fields=["served_at"])
    return directive


def get_sync_cursor(school, direction):
    """The stored high-water for ``school``/``direction``, or ``None`` for "everything".

    Never raises: a cursor read must not be able to break a sync cycle, and ``None``
    (re-send everything) is always the safe answer.
    """
    if school is None:
        return None
    try:
        row = EdgeSyncCursor.objects.filter(school=school, direction=direction).first()
    except Exception:  # noqa: BLE001 — a cursor read must never break a cycle
        return None
    return row.high_water if row is not None else None


def set_sync_cursor(school, direction, value):
    """Persist ``value`` as the high-water for ``school``/``direction``.

    Only ever moves FORWARD. An out-of-order or stale value (e.g. a page whose
    high-water precedes one already recorded) is ignored rather than rewinding the
    cursor, which would re-ship work already confirmed applied.
    """
    if school is None or value is None:
        return
    current = get_sync_cursor(school, direction)
    if current is not None and value <= current:
        return
    EdgeSyncCursor.objects.update_or_create(
        school=school, direction=direction, defaults={"high_water": value}
    )


def reset_sync_cursors(school, *, direction=""):
    """Rewind to "no position" so the next cycle re-sends/re-requests EVERYTHING.

    This is the full-resync primitive: the honest way to reconcile a box that has
    drifted or was restored from a backup is to replay the whole corpus through the
    normal, idempotent apply path rather than to hand-patch rows. Returns how many
    cursor rows were rewound.
    """
    qs = EdgeSyncCursor.objects.filter(school=school)
    if direction:
        qs = qs.filter(direction=direction)
    return qs.update(high_water=None)


def record_sync_apply(school_id, entity_type, pk, applied_updated_at, origin=""):
    """Upsert the provenance marker for a row just written by the sync apply path.

    ``school_id`` (not a School instance) so callers on the hot apply path need not
    load the School. No-op-safe to call once per applied row.
    """
    if not school_id or pk is None:
        return
    SyncApplyLedger.objects.update_or_create(
        school_id=school_id,
        entity_type=entity_type,
        local_pk=str(pk),
        defaults={"applied_updated_at": applied_updated_at, "origin": (origin or "")[:32]},
    )


def sync_echo_updated_at_map(school, entity_type) -> dict:
    """``{local_pk(str): applied_updated_at}`` for one school+entity.

    The delta builder loads this once per entity and skips any row whose current
    ``updated_at`` still equals the recorded value (an echo). Use ``.get(pk, _MISSING)``
    and compare against :data:`_MISSING` so a null-updated_at row is never wrongly
    suppressed.
    """
    return dict(
        SyncApplyLedger.objects.filter(school=school, entity_type=entity_type).values_list(
            "local_pk", "applied_updated_at"
        )
    )


__all__ = [
    "SyncApplyLedger",
    "EdgeSyncRun",
    "EdgeSyncCursor",
    "EdgeSyncDirective",
    "request_full_resync",
    "claim_pending_directive",
    "get_sync_cursor",
    "set_sync_cursor",
    "reset_sync_cursors",
    "record_sync_apply",
    "sync_echo_updated_at_map",
    "_MISSING",
]
