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


__all__ = ["SyncApplyLedger", "record_sync_apply", "sync_echo_updated_at_map", "_MISSING"]
