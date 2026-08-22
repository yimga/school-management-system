"""What the cloud knows about each box — kept, instead of thrown away.

Every box already tells the cloud what it is. `X-RMC-Sync-Manifest` rides every handshake,
`X-RMC-Sync-Engine` names the build, and `X-RMC-Sync-Upgrade-Failure` carries the reason an
upgrade stopped. All three were read and DISCARDED: the manifest hash was compared and
dropped, and the failure was written to a logfile. So the question an operator actually
asks — *which schools are on which release, and which one is stuck* — had no answer
anywhere, and the honest way to get one was to ask each school to read a screen.

`EdgeDeploymentHistory` cannot answer it either, and that is not a defect: it is written on
the BOX, in the box's own database, and the cloud never sees a row of it. It is the ladder
a box climbs back down alone at 02:00 with no network. This table is the other half — what
the cloud observed, recorded where an operator can read it.

ONE ROW PER SCHOOL, OVERWRITTEN. Deliberately not append-only, and the contrast with
`EdgeDeploymentHistory` is the point: that one is an audit trail whose value is that old
rows survive, so a rollback has something to aim at. This one is a *current state* readout,
and a row per handshake per school would be millions of rows a year to answer "what is it
on now". The durable history of what a box actually ran lives on the box.

WRITES ON A READ PATH, BOUNDED. Recording happens during an ordinary sync handshake, so it
is one small UPDATE per cycle per school — cycles are minutes apart, and the write is
skipped entirely when nothing changed, so a steady fleet costs a SELECT. It is wrapped so a
failure here can never cost a box its data: the whole point of the sync rail is moving a
school's records, and observability that can break it is worse than no observability.
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone


class EdgeFleetState(models.Model):
    """The last thing this school's box said about itself."""

    school = models.OneToOneField(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="edge_fleet_state",
    )

    # What the box reports it IS.
    reported_manifest_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    reported_engine = models.CharField(max_length=64, blank=True, default="")
    # What the cloud last offered it. Differs from reported_* while an upgrade is pending,
    # and differs FOREVER when a box cannot take the lane it needs — which is exactly the
    # row an operator wants to find.
    offered_manifest_hash = models.CharField(max_length=64, blank=True, default="")

    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # When the box last reported a hash DIFFERENT from the one before it, i.e. when it
    # actually moved. A box "seen 4 minutes ago" that last moved in June is healthy on the
    # network and stuck on the upgrade, and those two facts must not share a column.
    last_manifest_change_at = models.DateTimeField(null=True, blank=True)

    # The last upgrade failure this box reported, if any. Cleared when it reports a hash
    # matching what it was offered, because a failure that outlives its own resolution is
    # an operator chasing a ghost.
    last_failure_text = models.CharField(max_length=500, blank=True, default="")
    last_failure_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "sync_engine"
        verbose_name = "Edge fleet state"
        verbose_name_plural = "Edge fleet state"

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"EdgeFleetState({self.school_id},{self.reported_manifest_hash[:12]})"

    @property
    def in_parity(self) -> bool:
        return bool(
            self.reported_manifest_hash
            and self.offered_manifest_hash
            and self.reported_manifest_hash == self.offered_manifest_hash
        )

    # ── writers ──────────────────────────────────────────────────────────────
    @classmethod
    def record_seen(cls, school, *, reported_hash="", engine="", offered_hash=""):
        """Note that this box checked in, and what it said it was.

        Never raises. Returns the row, or ``None`` when the write could not happen —
        observability must not be able to cost a school its data sync.
        """
        if school is None:
            return None
        try:
            now = timezone.now()
            row, created = cls.objects.get_or_create(school=school)
            changed = ["last_seen_at"]
            row.last_seen_at = now

            reported = str(reported_hash or "")[:64]
            if reported and reported != row.reported_manifest_hash:
                row.reported_manifest_hash = reported
                row.last_manifest_change_at = now
                changed += ["reported_manifest_hash", "last_manifest_change_at"]

            engine = str(engine or "")[:64]
            if engine and engine != row.reported_engine:
                row.reported_engine = engine
                changed.append("reported_engine")

            offered = str(offered_hash or "")[:64]
            if offered != row.offered_manifest_hash:
                row.offered_manifest_hash = offered
                changed.append("offered_manifest_hash")

            # A box that arrived on what it was offered has resolved whatever went wrong.
            if reported and offered and reported == offered and row.last_failure_text:
                row.last_failure_text = ""
                row.last_failure_at = None
                changed += ["last_failure_text", "last_failure_at"]

            row.save(update_fields=changed if not created else None)
            return row
        except Exception:  # noqa: BLE001 - never cost the box its data for a readout
            return None

    @classmethod
    def record_failure(cls, school, *, text):
        """Keep the reason an upgrade stopped, where a person can find it."""
        if school is None or not str(text or "").strip():
            return None
        try:
            row, created = cls.objects.get_or_create(school=school)
            row.last_failure_text = str(text)[:500]
            row.last_failure_at = timezone.now()
            row.save(
                update_fields=None if created else ["last_failure_text", "last_failure_at"]
            )
            return row
        except Exception:  # noqa: BLE001
            return None


__all__ = ["EdgeFleetState"]
