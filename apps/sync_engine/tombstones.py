"""Deletion propagation: record a deleted row so its absence can cross the sync boundary.

THE GAP. The edge delta is built by scanning ``filter(updated_at__gt=since)``. A row that
was DELETED leaves nothing to scan, so a deletion was the one change the engine could not
carry in either direction. A student withdrawn on the cloud stayed enrolled on the
appliance; a classroom deleted on the appliance came back on the next pull; a revoked
invoice stayed payable offline. Every field converged and the absence of a row did not.

THE MECHANISM. A ``post_delete`` receiver on every registered synced model writes a
:class:`~apps.sync_engine.models.SyncTombstone`. Tombstones then ride the EXISTING rail:
:func:`iter_tombstone_rows` emits them as ordinary bundle rows carrying ``op="delete"``
and using ``deleted_at`` as their ``updated_at``, so the global updated_at ordering that
makes a page boundary a safe cursor keeps working unchanged, and the receiver applies
them through :func:`apps.api.sync_services.apply_deletes`.

Using ``post_delete`` rather than soft-delete columns is deliberate: it captures deletes
that ALREADY HAPPEN throughout the product - including CASCADES and queryset deletes,
which no ``is_deleted`` column would ever be set by - without editing a single call site.
See :class:`SyncTombstone` for the full rationale.

SAFETY. Deletion is the only sync operation that is not self-healing: a wrongly
propagated delete destroys data on the far side, and the far side has nothing left to
re-offer. Three guards, in order of how much they matter:

  1. **Policy.** A delete is a write, so it answers to ``policy_registry`` exactly like
     one. A money/grade/identity entity is cloud-authoritative, so a delete of one
     travelling UPWARD is refused - and the cloud then re-asserts the row (see
     ``apps.api.sync_services.apply_deletes``) so the appliance gets it back instead of
     the two sides diverging silently.
  2. **A flood guard.** One bundle may carry at most
     ``RMC_SYNC_MAX_DELETES_PER_BUNDLE`` deletions. Above that the whole delete batch is
     refused and reported. A runaway script or a mistaken bulk action on one side then
     costs a loud refusal instead of a mirrored wipe.
  3. **A kill switch.** ``RMC_SYNC_DELETE_PROPAGATION_ENABLED=0`` stops tombstones being
     recorded and shipped, leaving the engine exactly as it behaved before.

Nothing here is retroactive: the table starts empty, so enabling this cannot delete
anything that was already gone. Only deletions from this point forward travel.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models.signals import post_delete
from django.utils import timezone

logger = logging.getLogger(__name__)

# The row shape's marker for "this row is a deletion, not an update".
DELETE_OP = "delete"

_DEFAULT_MAX_DELETES_PER_BUNDLE = 500  # magic-number-allow: delete flood-guard default
_DEFAULT_TOMBSTONE_RETENTION_DAYS = 365  # magic-number-allow: tombstone retention default

# Set while THIS process is applying a deletion that arrived in a bundle, so the
# post_delete receiver records the provenance rather than presenting the deletion as
# locally originated. A plain module global is correct here: the apply path is
# synchronous within one cycle, and the worst case if it were ever wrong is a tombstone
# marked local - one extra echo, never a lost or spurious delete.
_APPLYING_REMOTE_DELETE = {"depth": 0}


def delete_propagation_enabled() -> bool:
    """Master switch. Default ON; ``RMC_SYNC_DELETE_PROPAGATION_ENABLED=0`` disables."""
    return bool(getattr(settings, "RMC_SYNC_DELETE_PROPAGATION_ENABLED", True))


def max_deletes_per_bundle() -> int:
    raw = getattr(
        settings, "RMC_SYNC_MAX_DELETES_PER_BUNDLE", _DEFAULT_MAX_DELETES_PER_BUNDLE
    )
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_DELETES_PER_BUNDLE


def tombstone_retention_days() -> int:
    raw = getattr(
        settings, "RMC_SYNC_TOMBSTONE_RETENTION_DAYS", _DEFAULT_TOMBSTONE_RETENTION_DAYS
    )
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return _DEFAULT_TOMBSTONE_RETENTION_DAYS


class applying_remote_delete:  # noqa: N801 - context manager, reads as a statement
    """Mark the enclosed block as applying a deletion that came from the far side."""

    def __enter__(self):
        _APPLYING_REMOTE_DELETE["depth"] += 1
        return self

    def __exit__(self, *exc):
        _APPLYING_REMOTE_DELETE["depth"] = max(0, _APPLYING_REMOTE_DELETE["depth"] - 1)
        return False


def _entity_type_by_model() -> dict:
    """``{model_class: entity_type}`` for every entity on the EDGE rail.

    Derived from the one registry that already decides what syncs
    (:func:`apps.api.sync_services._get_entity_config`), so an entity added there gets
    delete propagation automatically - the alternative, a second hand-maintained list,
    would drift, and the drift would stay invisible until a delete silently failed to
    travel.
    """
    from apps.api.sync_services import _get_entity_config

    return {
        model: entity
        for entity, (model, _fields) in _get_entity_config(include_derived=True).items()
    }


def record_tombstone(
    school_id, entity_type, local_pk, *, deleted_at=None, client_offline_id="", origin="",
    only_if_absent=False,
):
    """Upsert the tombstone for one deleted row. Never raises.

    ``only_if_absent`` leaves an EXISTING tombstone untouched. That is what the
    ``post_delete`` receiver passes while a remote deletion is being applied: the apply
    path has already recorded the burial with the far side's ORIGINAL timestamp, and
    re-stamping it with the local clock would destroy the one property delete-dominance
    depends on - both sides agreeing on when the row died. A CASCADE child, which has no
    tombstone of its own yet, is still created (with ``now``, correctly: this side is
    where that particular row died).

    Returns the tombstone, or ``None`` when nothing was recorded (propagation disabled,
    no tenant scope, or the table is not there yet - which is the normal state during the
    migration that creates it).
    """
    from apps.sync_engine.models import SyncTombstone

    if not delete_propagation_enabled() or not school_id or local_pk is None:
        return None
    defaults = {
        "deleted_at": deleted_at or timezone.now(),
        "client_offline_id": (client_offline_id or "")[:64],
        "origin": (origin or "")[:32],
    }
    try:
        if only_if_absent:
            obj, _created = SyncTombstone.objects.get_or_create(
                school_id=school_id,
                entity_type=entity_type,
                local_pk=str(local_pk),
                defaults=defaults,
            )
            return obj
        obj, _created = SyncTombstone.objects.update_or_create(
            school_id=school_id,
            entity_type=entity_type,
            local_pk=str(local_pk),
            defaults=defaults,
        )
        return obj
    except Exception:  # noqa: BLE001 - recording a tombstone must never break a delete
        logger.debug(
            "could not record tombstone for %s:%s", entity_type, local_pk, exc_info=True
        )
        return None


def _on_post_delete(sender, instance, **_kwargs):
    """``post_delete`` receiver. Deliberately total: it must never raise inside a delete."""
    try:
        if not delete_propagation_enabled():
            return
        entity_type = _entity_type_by_model().get(sender)
        if not entity_type:
            return
        school_id = getattr(instance, "school_id", None)
        if not school_id:
            return
        remote = bool(_APPLYING_REMOTE_DELETE["depth"])
        record_tombstone(
            school_id,
            entity_type,
            instance.pk,
            deleted_at=timezone.now(),
            client_offline_id=getattr(instance, "client_offline_id", "") or "",
            origin="remote" if remote else "",
            # While applying a remote deletion the apply path has ALREADY written the
            # burial with the far side's original timestamp. Overwriting it with the local
            # clock here would make the recorded death time depend on when each side
            # happened to sync, which is precisely what delete-dominance must not depend
            # on. A cascade CHILD has no tombstone yet, so it is still created.
            only_if_absent=remote,
        )
    except Exception:  # noqa: BLE001 - a delete must succeed even if we cannot record it
        logger.debug("tombstone receiver failed for %s", sender, exc_info=True)


_REGISTERED = {"done": False}


def register_delete_signals() -> int:
    """Connect the ``post_delete`` receiver to every registered synced model.

    Called from ``SyncEngineConfig.ready()``. Idempotent, and never raises: a signal
    wiring failure at import time would take down the whole deployment, which is a far
    worse outcome than deletions not propagating.
    """
    if _REGISTERED["done"]:
        return 0
    count = 0
    try:
        for model in _entity_type_by_model():
            post_delete.connect(
                _on_post_delete,
                sender=model,
                dispatch_uid=f"sync_engine.tombstone.{model._meta.label_lower}",
            )
            count += 1
        _REGISTERED["done"] = True
    except Exception:  # noqa: BLE001 - never break app startup
        logger.warning("could not register sync tombstone signals", exc_info=True)
    return count


def iter_tombstone_rows(school, *, since=None, entities=None):
    """Bundle rows for deletions since ``since`` - ``(rows, high_water)``.

    A tombstone row is an ordinary delta row carrying ``op="delete"`` and using
    ``deleted_at`` as its ``updated_at``, so it sorts into the same global chronological
    order every other row does and a page boundary stays a valid cursor position.
    """
    from apps.sync_engine.models import SyncTombstone

    if not delete_propagation_enabled():
        return [], None
    want = {str(e).strip().lower() for e in (entities or []) if str(e).strip()}
    rows: list[dict] = []
    high_water = None
    try:
        qs = SyncTombstone.objects.filter(school=school)
        if since is not None:
            qs = qs.filter(deleted_at__gt=since)
        if want:
            qs = qs.filter(entity_type__in=sorted(want))
        for tomb in qs.order_by("deleted_at").iterator():
            if high_water is None or tomb.deleted_at > high_water:
                high_water = tomb.deleted_at
            rows.append(
                {
                    "entity_type": tomb.entity_type,
                    "id": tomb.local_pk,
                    "client_offline_id": tomb.client_offline_id or "",
                    "op": DELETE_OP,
                    "changes": {},
                    "updated_at": tomb.deleted_at.isoformat() if tomb.deleted_at else None,
                }
            )
    except Exception:  # noqa: BLE001 - a tombstone read must never break a cycle
        logger.warning("could not read tombstones for the delta", exc_info=True)
        return [], None
    return rows, high_water


def tombstone_index(school_id, entity_types=(), local_pks=None) -> dict:
    """``{(entity_type, str(pk)): deleted_at}`` for the delete-dominance guard.

    Loaded ONCE per bundle. The guard it feeds is what makes delete-dominance
    order-independent: an incoming update for a row this side has buried is refused
    unless the update is strictly NEWER than the burial, in which case the far side is
    deliberately resurrecting the row and wins.

    ``local_pks`` scopes the read to the pks the CALLER is actually about to apply.
    Tombstones only ever accumulate — a school can hold a year of them — so loading the
    whole table to answer a question about at most a few hundred rows would make every
    apply slower in proportion to how long the deployment has been running. Passing the
    bundle's own keys keeps the read bounded by the BUNDLE, which is the right size.
    """
    from apps.sync_engine.models import SyncTombstone

    if not school_id:
        return {}
    try:
        qs = SyncTombstone.objects.filter(school_id=school_id)
        wanted = {str(e).strip().lower() for e in entity_types if str(e).strip()}
        if wanted:
            qs = qs.filter(entity_type__in=sorted(wanted))
        if local_pks:
            qs = qs.filter(local_pk__in=sorted({str(p) for p in local_pks if p is not None}))
        return {
            (row[0], row[1]): row[2]
            for row in qs.values_list("entity_type", "local_pk", "deleted_at")
        }
    except Exception:  # noqa: BLE001 - never break an apply
        logger.debug("could not load the tombstone index", exc_info=True)
        return {}


def tombstone_index_by_client_offline_id(school_id, anchors=None) -> dict:
    """``{(entity_type, client_offline_id): deleted_at}`` - the insert path's guard.

    A row CREATED offline is matched by ``(school, client_offline_id)``, never by pk, so
    the pk-keyed index cannot answer "has this been buried?" for it. Without this second
    index a box could re-create, on every single cycle, a row the cloud had already
    deleted - the upsert would find no row, insert a fresh one, and the cloud would
    delete it again.
    """
    from apps.sync_engine.models import SyncTombstone

    if not school_id:
        return {}
    try:
        qs = SyncTombstone.objects.filter(school_id=school_id).exclude(client_offline_id="")
        if anchors:
            # Same reasoning as tombstone_index: bound the read by the bundle, not by how
            # long this deployment has been recording deletions.
            qs = qs.filter(client_offline_id__in=sorted({str(a) for a in anchors if a}))
        rows = qs.values_list("entity_type", "client_offline_id", "deleted_at")
        return {(r[0], r[1]): r[2] for r in rows}
    except Exception:  # noqa: BLE001 - never break an apply
        logger.debug("could not load the client_offline_id tombstone index", exc_info=True)
        return {}


def clear_tombstone(school_id, entity_type, local_pk) -> int:
    """Forget one burial - used when the far side legitimately resurrects a row."""
    from apps.sync_engine.models import SyncTombstone

    if not school_id or local_pk is None:
        return 0
    try:
        return SyncTombstone.objects.filter(
            school_id=school_id, entity_type=entity_type, local_pk=str(local_pk)
        ).delete()[0]
    except Exception:  # noqa: BLE001
        logger.debug(
            "could not clear tombstone %s:%s", entity_type, local_pk, exc_info=True
        )
        return 0


def prune_tombstones(school=None, *, older_than_days=None) -> int:
    """Drop tombstones past the retention window. Returns how many were removed.

    A tombstone only has to survive long enough for every peer to have seen it. Past
    that a box has been dark for longer than the window and a full resync - which
    reconciles by CONTENT, not by replaying history - is the correct repair anyway.
    """
    from apps.sync_engine.models import SyncTombstone

    days = int(older_than_days or tombstone_retention_days())
    cutoff = timezone.now() - timedelta(days=days)
    try:
        # tenant-isolation-allow: retention-sweep-is-intentionally-all-schools-when-no-school-given
        qs = SyncTombstone.objects.filter(deleted_at__lt=cutoff)
        if school is not None:
            qs = qs.filter(school=school)
        return qs.delete()[0]
    except Exception:  # noqa: BLE001
        logger.debug("tombstone prune failed", exc_info=True)
        return 0


__all__ = [
    "DELETE_OP",
    "applying_remote_delete",
    "clear_tombstone",
    "delete_propagation_enabled",
    "iter_tombstone_rows",
    "max_deletes_per_bundle",
    "prune_tombstones",
    "record_tombstone",
    "register_delete_signals",
    "tombstone_index",
    "tombstone_index_by_client_offline_id",
    "tombstone_retention_days",
]
