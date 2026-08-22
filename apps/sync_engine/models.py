"""Sync-engine models.

Most sync domain logic lives in services.py; offline queue rows use
apps.api.mobile_api.OfflineSyncQueue. The one persistent model here is the
echo-suppression ledger that makes edge<->cloud sync BIDIRECTIONAL without an
infinite ping-pong of sync-applied rows.
"""
from __future__ import annotations

import logging

from django.db import models

logger = logging.getLogger(__name__)

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


class SyncTombstone(models.Model):
    """A row that was DELETED, recorded so the deletion can cross the sync boundary.

    THE HOLE THIS CLOSES. The delta is built by scanning ``filter(updated_at__gt=since)``.
    A deleted row leaves nothing to scan, so a deletion was the one change the engine
    could never carry: a withdrawn student stayed enrolled on the appliance forever, a
    revoked invoice stayed payable, a mis-created classroom could be removed on the cloud
    and would silently come back to life on the box. Every other field converged; the
    absence of a row did not.

    WHY A TOMBSTONE TABLE AND NOT ``is_deleted`` COLUMNS. The obvious alternative is soft
    deletion on each synced model. It is worse here for three concrete reasons:

      * it would require a migration on fifteen live TENANT business tables, and every
        existing ``.delete()`` call site in the product would have to be rewritten or the
        column would simply never be set - a silent, partial rollout of the exact
        guarantee we are trying to make total;
      * a database-level CASCADE (deleting a department removes its specialties) fires
        ``post_delete`` for every child but would never set anyone's ``is_deleted``, so
        cascades - the most common way rows actually disappear - would still not travel;
      * ``.delete()`` already happens throughout the product today. A ``post_delete``
        receiver captures all of it, including cascades and queryset deletes, with no
        change to a single call site.

    The cost is honest and bounded: a tombstone is a fact about the past, so this table
    only grows. :func:`prune_tombstones` trims rows older than the retention window - long
    enough that a box offline for a term still learns about every deletion, after which a
    full resync is the correct repair anyway.

    ``deleted_at`` is SET, never ``auto_now``: when this side applies a tombstone that
    arrived in a bundle it preserves the ORIGINAL deletion time. That is what makes
    delete-dominance resolve to the same answer no matter which side is asked first, and
    it is what lets the cloud re-assert authority over a refused delete by writing a
    strictly newer row.

    TENANCY mirrors :class:`SyncApplyLedger` - one SHARED/public-schema table
    discriminated by the ``school`` FK.
    """

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="sync_tombstones"
    )
    entity_type = models.CharField(max_length=64)
    # str(pk) for the same reason SyncApplyLedger.local_pk is a char column: entity pks
    # are int on most models and uuid on some, and one column has to hold both.
    local_pk = models.CharField(max_length=64)
    # Carried so the far side can also match a row that was CREATED offline and never had
    # a portable pk. Empty for cloud-authored rows.
    client_offline_id = models.CharField(max_length=64, blank=True, default="")
    deleted_at = models.DateTimeField(db_index=True)
    # "" when this side deleted the row itself; "cloud-pull" / "edge-push" when the
    # deletion arrived in a bundle. Observability - the rail does not branch on it.
    origin = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        app_label = "sync_engine"
        ordering = ["deleted_at"]
        verbose_name = "Sync tombstone"
        verbose_name_plural = "Sync tombstones"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "entity_type", "local_pk"], name="uq_synctombstone_row"
            )
        ]
        indexes = [models.Index(fields=["school", "deleted_at"])]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"deleted {self.entity_type}:{self.local_pk}@{self.deleted_at}"


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
    # Rows the far side sent that this side could NOT apply: an absent parent, an entity
    # held from creation, a value the local schema refuses. Distinct from `conflicts`
    # (where a human is being asked to choose) and NOT visible in `pulled`, which counts
    # rows RECEIVED. Without it a pull that refused every row rendered as a green cycle.
    skipped = models.IntegerField(default=0)
    # Rows REMOVED by a deletion that crossed the boundary. Counted apart from every
    # other number here because it is the only one that destroys data: an operator
    # reading a cycle summary has to be able to see, at a glance, that this cycle
    # deleted things.
    deleted = models.IntegerField(default=0)
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
        from django.utils import timezone as _tz

        valid = {f.name for f in cls._meta.concrete_fields}
        clean = {k: v for k, v in kw.items() if k in valid and k != "school"}
        now = _tz.now()
        clean.setdefault("started_at", now)
        clean.setdefault("finished_at", now)
        return cls.objects.create(school=school, **clean)

    @classmethod
    def latest_for(cls, school):
        """The most recent run for ``school`` (``Meta.ordering`` is newest-first), or None."""
        if school is None:
            return None
        return cls.objects.filter(school=school).first()

    @classmethod
    def in_progress_for(cls, school):
        """The newest unfinished cycle for ``school``, or None.

        ``finished_at`` is the live signal — a cycle that has started but not
        recorded an outcome yet. Used by Sync Center so a queued/running cycle
        is not hidden behind an older failed row.
        """
        if school is None:
            return None
        return (
            cls.objects.filter(school=school, finished_at__isnull=True)
            .order_by("-created_at")
            .first()
        )

    @classmethod
    def begin(cls, school, *, mode="live"):
        """Open one in-progress row. Stale unfinished rows are closed first.

        Exactly one cycle is meant to run at a time per school on a box. A
        previous row left with ``finished_at`` NULL (crash, SIGKILL) would
        otherwise pin the UI on "running" forever.
        """
        from django.utils import timezone as _tz

        now = _tz.now()
        cls.objects.filter(school=school, finished_at__isnull=True).update(
            finished_at=now,
            ok=False,
            error="abandoned: a newer cycle started",
        )
        return cls.objects.create(
            school=school,
            mode=mode,
            ok=False,
            message="running",
            started_at=now,
            finished_at=None,
        )

    def checkpoint(self, **kw):
        """Persist mid-cycle counts so status polling can read real progress."""
        valid = {f.name for f in self._meta.concrete_fields}
        dirty = []
        for key, value in kw.items():
            if key in valid and key not in {"school", "id", "pk", "created_at"}:
                setattr(self, key, value)
                dirty.append(key)
        if dirty:
            self.save(update_fields=dirty)
        return self

    def complete(self, **kw):
        """Stamp the outcome onto THIS row so tests still see exactly one run."""
        from django.utils import timezone as _tz

        valid = {f.name for f in self._meta.concrete_fields}
        for key, value in kw.items():
            if key in valid and key not in {"school", "id", "pk", "created_at"}:
                setattr(self, key, value)
        if self.finished_at is None:
            self.finished_at = _tz.now()
        self.save()
        return self


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


class SyncBundleReceipt(models.Model):
    """One row per bundle this side has ALREADY accepted - the replay defence.

    An HMAC signature proves a bundle was built by someone holding the signing key. It
    proves nothing about whether this is the FIRST time you have been handed it. Anyone
    who can observe or store a bundle - a LAN data-mule USB stick, a proxy, a backup of
    the box's spool directory - can present the identical bytes again later, and the
    signature verifies perfectly every time.

    For most rows a replay is merely wasteful, because the apply path is idempotent. It
    is NOT harmless for the ones that are not pure state: a replayed bundle can
    resurrect a row the far side has since deleted (the bundle predates the tombstone),
    or re-apply a value a human has since resolved a conflict away from. Replay defence
    is what makes "the far side accepted this" a fact about one delivery rather than
    about a payload.

    Every bundle carries a random ``nonce`` in its (signed) header. Presenting a nonce
    this school has already accepted is refused. A sender too old to emit one falls back
    to the payload digest, so an unmodified appliance keeps working while still being
    protected against a byte-identical replay.

    The table is pruned to ``RMC_SYNC_BUNDLE_REPLAY_WINDOW_SECONDS``, which is therefore
    exactly how far back the guarantee reaches - and why a bundle older than the window
    is refused rather than accepted with lapsed protection.
    """

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="sync_bundle_receipts"
    )
    # The header nonce, or the sha256 of the payload for a sender that predates it.
    nonce = models.CharField(max_length=64)
    row_count = models.IntegerField(default=0)
    # "edge-push" (a box's bundle, seen by the cloud) | "cloud-pull" (the reverse).
    direction = models.CharField(max_length=16, blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "sync_engine"
        verbose_name = "Sync bundle receipt"
        verbose_name_plural = "Sync bundle receipts"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "nonce"], name="uq_syncbundlereceipt_school_nonce"
            )
        ]
        indexes = [models.Index(fields=["school", "received_at"])]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"SyncBundleReceipt({self.direction},{self.nonce[:12]})"


class SyncFileTransfer(models.Model):
    """One file that has to cross the boundary, and how far it has got.

    THE GAP. ``_derive_sync_fields`` drops every ``FileField``, correctly: a delta bundle
    carries column VALUES, so shipping a stored path would point the far side at a file
    that does not exist on it and the apply would report a clean 200 over a broken
    reference. The consequence is that student photos, scanned report cards and payment
    proofs simply do not exist across the boundary - a parent's payment proof uploaded
    offline is invisible to the bursar on the cloud, and vice versa.

    DELIBERATELY OFF THE ROW RAIL. Files move through their own endpoints, their own
    queue and their own command. A 50 MB attachment on a village link takes minutes; if
    that shared a cycle with the data rail, every data cycle would inherit the slowest
    file on the box, and a failed upload would fail the cycle. Keeping them apart is what
    lets attendance keep converging in seconds while a scan crawls up in the background.

    RESUMABLE BY CONSTRUCTION. ``bytes_done`` is the durable offset, so a transfer that
    dies at 80% resumes at 80% rather than starting over - the difference between "this
    file will eventually arrive" and "this file never arrives" on an intermittent link.
    ``sha256`` is verified before the file is committed to storage, so a truncated or
    corrupted transfer can never be mistaken for a complete one.
    """

    PULL = "pull"
    PUSH = "push"

    class State(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACTIVE = "ACTIVE", "In progress"
        DONE = "DONE", "Complete"
        FAILED = "FAILED", "Failed"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="sync_file_transfers"
    )
    # "pull" (cloud -> box) | "push" (box -> cloud).
    direction = models.CharField(max_length=8)
    # The storage-relative name, identical on both sides because the appliance is a
    # pk-preserving clone and stores under the same keys.
    relative_path = models.CharField(max_length=500)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    size_bytes = models.BigIntegerField(default=0)
    bytes_done = models.BigIntegerField(default=0)
    state = models.CharField(max_length=8, choices=State.choices, default=State.PENDING)
    attempts = models.IntegerField(default=0)
    last_error = models.CharField(max_length=255, blank=True, default="")
    # Provenance, for the operator surface: which record's which field this file is.
    entity_type = models.CharField(max_length=64, blank=True, default="")
    local_pk = models.CharField(max_length=64, blank=True, default="")
    field_name = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "sync_engine"
        ordering = ["created_at"]
        verbose_name = "Sync file transfer"
        verbose_name_plural = "Sync file transfers"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "direction", "relative_path"],
                name="uq_syncfiletransfer_target",
            )
        ]
        indexes = [models.Index(fields=["school", "state"])]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"{self.direction} {self.relative_path} ({self.state})"


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
    # An OTA upgrade OFFER. Unlike full-resync this is a RECORD, not an instruction: the
    # box acts on the X-RMC-Sync-Manifest-Target header, which is stateless and therefore
    # always current. The row exists so a cloud operator can see "offered on Tuesday, box
    # has not come back" — a question a stateless header cannot answer. It is excluded
    # from claim_pending_directive for exactly that reason: serving it would mark it and
    # mint a fresh one on the next poll, turning a stalled box into an unbounded log.
    UPGRADE = "upgrade"

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
        _wake_any_listening_box(school)
        return pending
    directive = EdgeSyncDirective.objects.create(
        school=school,
        kind=EdgeSyncDirective.FULL_RESYNC,
        requested_by=user if getattr(user, "pk", None) else None,
    )
    _wake_any_listening_box(school)
    return directive


def _wake_any_listening_box(school) -> None:
    """Nudge the long-poll changes feed so a held-open box returns NOW.

    The feed's in-loop check consults an in-memory beacon that only data writes bump,
    so without this a box sitting in a 25-second hold would not notice a directive that
    was queued one second into it. Best-effort by construction: if the beacon is
    unavailable the box still collects the directive on its next ordinary poll, which
    is the behaviour that existed before this call.
    """
    try:
        from apps.sync_engine.change_beacon import bump

        bump(getattr(school, "pk", None), force=True)
    except Exception:  # noqa: BLE001 — a missed nudge costs latency, never correctness
        logger.debug("request_full_resync: could not bump the change beacon", exc_info=True)


def claim_pending_directive(school):
    """Hand the box its oldest un-served directive and mark it served, or ``None``.

    Called by the download endpoint while it is already serving the box, so the
    directive rides an existing round trip rather than needing a channel of its own.
    """
    from django.utils import timezone as _tz

    directive = (
        EdgeSyncDirective.objects.filter(school=school, served_at__isnull=True)
        .exclude(kind=EdgeSyncDirective.UPGRADE)  # an offer, not an instruction — see UPGRADE
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


def cursor_overlap_seconds() -> int:
    """How far BEHIND the stored high-water a cycle actually asks from.

    ``RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS`` (default 120). ``0`` restores the exact
    previous behaviour. See :func:`get_sync_cursor_for_request` for why it exists.
    """
    from django.conf import settings

    try:
        return max(0, int(getattr(settings, "RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS", 120)))
    except (TypeError, ValueError):
        return 120


def get_sync_cursor_for_request(school, direction):
    """The position a cycle should ASK from - the stored high-water, minus an overlap.

    THE TWO HOLES IN A WALL-CLOCK CURSOR. ``updated_at``-scanning is not a transactional
    outbox, and it misses changes in two ways that are invisible when they happen:

      1. **The commit-after-read race.** A transaction that STARTS before a cycle reads
         the high-water but COMMITS after it stamps an ``updated_at`` that is already
         behind the recorded position. The next cycle asks for everything strictly newer
         than that position, so the row is never offered again. Not delayed - lost, until
         something unrelated touches it.
      2. **Ties at a page boundary.** Two rows written inside the same clock tick, split
         across a page: the cursor advances to that timestamp and ``__gt`` then excludes
         the twin that has not shipped.

    Re-asking from slightly BEHIND the cursor closes both, for any transaction shorter
    than the overlap. That bound is real and worth stating plainly: a transaction that
    stays open longer than the window can still slip through, and only a monotonic
    sequence written in the same transaction as the business row would close it
    completely. The trade is deliberate - the overlap costs a few re-shipped rows per
    cycle, and every apply path here is idempotent (update-by-pk, upsert-by-anchor,
    create-by-pk), so a re-shipped row costs bandwidth and never correctness. A sequence
    column would cost a migration on fifteen live tenant tables.

    Echo suppression keeps the cost near zero in practice: a row re-offered inside the
    overlap that sync itself last wrote is dropped by the ledger before it is ever
    serialized.
    """
    from datetime import timedelta

    high_water = get_sync_cursor(school, direction)
    if high_water is None:
        return None
    overlap = cursor_overlap_seconds()
    return high_water - timedelta(seconds=overlap) if overlap else high_water


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


# Tenant-owned schedule rules. Defined in their own module for readability, re-exported
# here because Django discovers models through ``<app>.models`` and the edge rail resolves
# entities with ``get_model("sync_engine", "SyncSchedule")``.
from apps.sync_engine.models_schedule import (  # noqa: E402
    SyncSchedule,
    format_days,
    format_times,
    parse_days,
    parse_times,
    rules_for,
)

# How the schedule behaves AROUND the rules (check-in ceiling, catch-up). Same reason as
# above: Django discovers models through ``<app>.models``.
from apps.sync_engine.models_policy import (  # noqa: E402
    SyncPolicy,
)

# Pairing lives in its own module (it is a protocol, not sync state) but must be
# imported here so Django's app registry discovers the model and makemigrations sees it.
from .models_pairing import (  # noqa: E402  (re-export for the registry)
    EdgeClaimTicket,
    EdgeCloudBinding,
    EdgePairingRequest,
    PendingPushConfirmation,
)

# What CODE this box has run, and which manifest it can fall back to. Box-level rather
# than tenant-level (no ``school`` FK) — see models_deployment for why.
from .models_deployment import (  # noqa: E402  (re-export for the registry)
    DeploymentState,
    EdgeDeploymentHistory,
)

# WHO may move to a new manifest yet. EdgeRolloutPolicy is per school (tenant-scoped, so
# it is enumerated in 0019_rollout_rls); ManifestRelease describes how far a RELEASE has
# been promoted, which is identical for every school, so it has no ``school`` FK.
from .models_rollout import (  # noqa: E402  (re-export for the registry)
    DEFAULT_RING,
    EdgeRolloutPolicy,
    ManifestRelease,
    RolloutRing,
    default_release_rings,
    may_receive,
)

__all__ = [
    "DeploymentState",
    "EdgeDeploymentHistory",
    "EdgeRolloutPolicy",
    "ManifestRelease",
    "RolloutRing",
    "DEFAULT_RING",
    "default_release_rings",
    "may_receive",
    "EdgeClaimTicket",
    "EdgeCloudBinding",
    "PendingPushConfirmation",
    "EdgePairingRequest",
    "SyncApplyLedger",
    "SyncPolicy",
    "SyncSchedule",
    "rules_for",
    "parse_days",
    "format_days",
    "parse_times",
    "format_times",
    "SyncTombstone",
    "SyncBundleReceipt",
    "SyncFileTransfer",
    "cursor_overlap_seconds",
    "get_sync_cursor_for_request",
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
