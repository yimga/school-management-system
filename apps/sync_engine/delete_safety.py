"""Delete safety: WHICH row a deletion names, and HOW MUCH of a table one bundle may take.

MEASURED ON A PRODUCTION APPLIANCE, 2026-09-02. One pull carried 46 tombstones: 39
``teacher`` (pks 28..66), 6 ``specialty_subject`` (pks 1..6), 1 ``sync_schedule``. The 39
teacher deletions were recorded on the cloud inside 220ms at 12:00:01 - one sweep, not a
term's staff turnover. NONE of them carried a ``client_offline_id``, so nothing could
match them except an integer minted on the far side. The run reported ``applied 75709 ...
deleted 0, conflicts 0, skipped 0`` and the sum was 46 short.

WHAT IS NOT KNOWN, said here because an earlier reading of this incident got it wrong and
the wrong version is the one that travels. That reading claimed 13 teacher records had
already been destroyed on a previous cycle, by subtracting 26 survivors from 39
tombstones. The pk ranges do not support it: the box's live teacher pks are 2..27 and the
tombstones cover 28..66, which are DISJOINT, so ``already_absent`` may be literally true
for all 39 and nothing lost at all. It is not disproven either - it is UNMEASURED, and the
measurement that would settle it has not been run. The 6 ``specialty_subject`` tombstones
are the ones to look at: pks 1..6 DO overlap where a small catalog's rows live.

NONE OF WHICH CHANGES THE DEFECT. Whether this bundle destroyed anything on this box is a
question about one box's luck. A pk-only deletion that cannot say which row it names is
wrong on every box, and deletion is the only sync operation that is not self-healing: the
far side has nothing left to re-offer, so a wrong match is not a divergence that converges
later, it is data that is gone.

THE ASSUMPTION THAT FAILED. :mod:`apps.sync_engine.parity` states the identity contract the
whole rail runs on, and states it in exactly two cases:

  * a row created on the CLOUD is pushed down by ``_create_from_cloud_pull``, which
    PRESERVES the operator's pk -- so the pk agrees on both sides and the anchor is empty;
  * a row created on the BOX is upserted by ``(school, client_offline_id)``, and the far
    side mints its OWN pk -- so the pks differ by construction and only the anchor agrees.

There is a THIRD case the contract does not name, and on a self-hosted box it is the
common one: a row created on the box through an ordinary online form. Nothing in the
product mints a ``client_offline_id`` on ``save()`` -- the anchor comes from the OFFLINE
capture path -- so such a row is anchor-less AND box-pk'd. It is indistinguishable, from
the row itself, from a cloud-authored row, and it is not one. The two deployments then
mint into the same integer space independently (the box is shared-DB + RLS, the cloud is
schema-per-tenant; their sequences have never been related), and a pk-only tombstone names
whatever happens to be sitting at that number over here.

WHAT COUNTS AS PROOF THAT A PK MEANS THE SAME ROW ON BOTH SIDES. Three answers were
considered and only one of them is derivable from what this deployment actually knows:

  * A PER-DEPLOYMENT SETTING ("this box is a verbatim clone") is a declaration, not a
    fact. It survives here only as an explicit override, defaulting OFF, because an
    operator who has restored a box from a cloud dump genuinely does know something the
    data does not record -- but nothing may depend on someone remembering to set it.
  * A PER-ENTITY PROPERTY (does the model carry an anchor column?) answers a different
    question. ``people.TeacherProfile`` HAS ``client_offline_id``; every one of the 39
    tombstones was empty anyway, because the rows were authored where nothing fills it in.
  * A SIGNAL ON THE BUNDLE cannot exist. The sender knows its own pk is portable-by-intent;
    what it cannot know is that the receiver has an unrelated row at the same number. The
    evidence has to live on the RECEIVING side, and it does.

:class:`apps.sync_engine.models.SyncApplyLedger` is that evidence, and it costs no new
configuration at all because it is already written on every apply. A ledger row for
``(school, entity_type, local_pk)`` means: the far side has ALREADY addressed this exact pk
on this side, and this side applied its content into the row at that pk. That is precisely
the trace the pk-preserving contract leaves behind -- ``_create_from_cloud_pull`` writes one
for every row the far side authored here, and ``apply_changes`` writes one for every row of
the far side's this side has ever taken an update from. A row minted locally that the far
side has never touched has no ledger row, which is exactly the shape that must not be
deleted by a foreign integer.

IT IS EVIDENCE, NOT A THEOREM, AND THE DIFFERENCE IS WORTH STATING. If the two sides ever
collided on a pk AND the update rail already applied across that collision, the ledger
records the collision as agreement. What that costs is bounded: the row's field values were
already overwritten by that update, which is a self-healing operation someone can undo. It
does not save a case that was already lost. What it does close is the case that was open --
a local row the far side has never addressed, destroyed by the far side's arithmetic.

FAIL CLOSED, AND SAY SO. Absent evidence is not permission. A pk-only deletion with no
ledger row is refused with :data:`REASON_PK_NOT_SHARED`, a 409 that ``tally_skipped_rows``
counts and the dead-letter table records per row, so the operator sees which rows and why
rather than a number that sums refusals and no-ops together. Nothing is lost by refusing:
the far side keeps its tombstone and re-offers it every cycle, so the deletion applies the
moment the evidence exists or the override is set.

THE SECOND GUARD IS PROPORTION, NOT COUNT. ``RMC_SYNC_MAX_DELETES_PER_BUNDLE`` defaults to
500 rows, so 39 deletions -- 100% of a school's teaching staff -- looked routine to it. A
count cannot tell a big school's routine churn from a small school's extinction. A FRACTION
can: see :func:`entities_over_delete_fraction`. It is per ENTITY because tables are deleted
from independently and one entity's wipe must not be averaged away by another's quiet
cycle, and it has a floor because on a table of three rows deleting two is ordinary and no
fraction is informative.
"""
from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

#: The local row carries an offline anchor and the incoming deletion does not. By the
#: identity contract those cannot be the same row: a row this side created offline is
#: matched everywhere by ``(school, client_offline_id)``, and the far side's copy of it --
#: if the far side has one at all -- carries that anchor, so its tombstone would too.
#: This refusal is PROVABLE from the two rows alone and needs no configuration.
REASON_ANCHOR_MISMATCH = "delete_anchor_mismatch"

#: A pk-only deletion naming a live local row that nothing on this side ties to the far
#: side. Honest about not knowing: the pk space is not PROVABLY shared, so the deletion is
#: refused rather than guessed at.
REASON_PK_NOT_SHARED = "delete_pk_not_provably_shared"

#: One bundle would delete more of an entity's live rows than the proportional guard
#: allows. Refused for that entity as a whole, exactly like the row-count flood guard.
REASON_PROPORTION_GUARD = "delete_proportion_guard"

# Platform-constant layer of the configurability cascade. Both values are overridable per
# tenant (School.settings) and per deployment (env var); see the resolvers below.
_DEFAULT_MAX_DELETE_FRACTION = 0.25  # magic-number-allow: proportional delete-guard default
_DEFAULT_MIN_LIVE_ROWS = 10  # magic-number-allow: proportional delete-guard floor

#: ``School.settings`` keys for the tenant layer of the cascade.
SCHOOL_SETTING_MAX_FRACTION = "sync_max_delete_fraction_per_bundle"
SCHOOL_SETTING_MIN_ROWS = "sync_delete_fraction_min_rows"


def trusts_peer_pks() -> bool:
    """Has this deployment DECLARED that its pk space is the far side's?

    Default False, and deliberately so: it is the one input here that is a statement of
    belief rather than a derivation, and a safety property that depends on somebody having
    remembered to set a variable is not a safety property. It exists because an operator
    who restored a box from a cloud dump really does know something the data does not
    record, and refusing them the deletion rail forever would be its own defect.

    ``RMC_SYNC_DELETE_TRUSTS_PEER_PKS=1`` turns pk-only deletion back on WHOLE. It does not
    weaken :data:`REASON_ANCHOR_MISMATCH`, which is provable from the rows themselves and
    no declaration can make true.
    """
    return bool(getattr(settings, "RMC_SYNC_DELETE_TRUSTS_PEER_PKS", False))


def _school_overrides(school_id) -> dict:
    """The tenant layer: ``School.settings``, read ONCE per bundle.

    Never raises and never blocks a cycle - a school row that cannot be read simply means
    the cascade falls through to the deployment and platform layers, which is the same
    answer a school with no override gives.
    """
    if not school_id:
        return {}
    try:
        from apps.schools.models import School

        raw = (
            School.objects.filter(pk=school_id)
            .values_list("settings", flat=True)
            .first()
        )
        return raw if isinstance(raw, dict) else {}
    except Exception:  # noqa: BLE001 - a config read must never break an apply
        logger.debug("could not read school delete-guard overrides", exc_info=True)
        return {}


def max_delete_fraction(overrides=None) -> float:
    """How much of ONE entity's live rows a single bundle may delete, as a fraction.

    Cascade, highest layer first: tenant ``School.settings`` -> deployment env var
    (``RMC_SYNC_MAX_DELETE_FRACTION_PER_BUNDLE``) -> platform constant. A value of 1.0 or
    more means "no proportional limit", which is how a deployment turns this guard off
    without turning the row-count flood guard off with it.
    """
    raw = (overrides or {}).get(SCHOOL_SETTING_MAX_FRACTION)
    if raw is None:
        raw = getattr(
            settings,
            "RMC_SYNC_MAX_DELETE_FRACTION_PER_BUNDLE",
            _DEFAULT_MAX_DELETE_FRACTION,
        )
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_DELETE_FRACTION
    # A zero or negative fraction would refuse every deletion of every entity above the
    # floor, which is the kill switch's job and not this one's.
    return value if value > 0 else _DEFAULT_MAX_DELETE_FRACTION


def min_live_rows_for_fraction_guard(overrides=None) -> int:
    """Below this many live rows the fraction is not evidence of anything.

    Deleting two of three classrooms is an ordinary Tuesday and reads as 67% of the table.
    The floor is what stops a proportional guard from being a small-school tax; above it,
    a fraction starts to mean what it says. Same cascade as :func:`max_delete_fraction`.
    """
    raw = (overrides or {}).get(SCHOOL_SETTING_MIN_ROWS)
    if raw is None:
        raw = getattr(
            settings, "RMC_SYNC_DELETE_FRACTION_MIN_ROWS", _DEFAULT_MIN_LIVE_ROWS
        )
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return _DEFAULT_MIN_LIVE_ROWS


def delete_fraction_policy(school_id) -> tuple[float, int]:
    """``(max_fraction, min_live_rows)`` for one school - one settings read per bundle."""
    overrides = _school_overrides(school_id)
    return max_delete_fraction(overrides), min_live_rows_for_fraction_guard(overrides)


def peer_addressed_pks(school_id, keys) -> set:
    """Which ``(entity_type, str(pk))`` the far side has already addressed HERE.

    Reads :class:`apps.sync_engine.models.SyncApplyLedger`, which the apply path writes on
    every applied row and only on an applied row. Bounded by the BUNDLE's own keys for the
    same reason ``tombstone_index`` is: the ledger grows with the deployment's whole life
    and the question is about at most a few hundred rows.

    THE INTERSECTION AT THE END IS NOT DECORATION. ``entity_type__in`` x ``local_pk__in``
    is a CROSS PRODUCT: a ledger row for ``("student", "7")`` would otherwise answer for
    ``("teacher", "7")`` as well, and this function's whole job is to be the thing that
    does not hand a deletion the wrong row.

    Returns an empty set on ANY failure. That is the fail-closed direction: no evidence
    read means no evidence, and no evidence means the deletion is refused.
    """
    from apps.sync_engine.models import SyncApplyLedger

    keys = {(str(e), str(p)) for e, p in (keys or ()) if e and p is not None}
    if not school_id or not keys:
        return set()
    try:
        rows = SyncApplyLedger.objects.filter(
            school_id=school_id,
            entity_type__in=sorted({e for e, _p in keys}),
            local_pk__in=sorted({p for _e, p in keys}),
        ).values_list("entity_type", "local_pk")
        return {(r[0], r[1]) for r in rows} & keys
    except Exception:  # noqa: BLE001 - never break an apply; refuse instead
        logger.debug("could not read the apply ledger for delete safety", exc_info=True)
        return set()


def entities_over_delete_fraction(
    targets_by_entity, live_by_entity, *, max_fraction, min_live_rows
) -> dict:
    """Which entities one bundle would take too large a share of. Pure arithmetic.

    ``targets_by_entity`` counts rows that would ACTUALLY delete something - not the
    deletion rows received. The difference is the whole usefulness of the guard on a real
    rail: a tombstone is re-offered on every cycle until its cursor passes, so counting
    received rows would refuse a box forever over deletions that already happened and
    would remove nothing now. "Would delete" is the number the operator's question is
    about.

    A table at or below ``min_live_rows`` is never guarded: see
    :func:`min_live_rows_for_fraction_guard`.

    Returns ``{entity_type: {"targets", "live", "fraction", "max_fraction",
    "min_live_rows"}}`` - the numbers, not a verdict, so the caller can put them in the
    refusal where an operator will read them.
    """
    over: dict = {}
    for entity_type, targets in (targets_by_entity or {}).items():
        targets = int(targets or 0)
        live = int((live_by_entity or {}).get(entity_type) or 0)
        if targets <= 0 or live < int(min_live_rows):
            continue
        fraction = targets / live
        if fraction <= float(max_fraction):
            continue
        over[entity_type] = {
            "targets": targets,
            "live": live,
            "fraction": round(fraction, 4),
            "max_fraction": float(max_fraction),
            "min_live_rows": int(min_live_rows),
        }
    return over


__all__ = [
    "REASON_ANCHOR_MISMATCH",
    "REASON_PK_NOT_SHARED",
    "REASON_PROPORTION_GUARD",
    "SCHOOL_SETTING_MAX_FRACTION",
    "SCHOOL_SETTING_MIN_ROWS",
    "delete_fraction_policy",
    "entities_over_delete_fraction",
    "max_delete_fraction",
    "min_live_rows_for_fraction_guard",
    "peer_addressed_pks",
    "trusts_peer_pks",
]
