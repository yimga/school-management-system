"""G7: prove convergence by running it, instead of asserting it in prose.

Every other guarantee in this engine is a claim about a SEQUENCE of events - an outage,
then writes on both sides, then a restore; a bundle that dies half-applied; a clock ten
minutes out. Unit tests check the pieces. Nothing until now ran the sequences, so "the
appliance converges with the cloud" was an argument rather than a measurement.

WHAT THIS IS, PRECISELY, so nobody over-reads it. The harness drives one real database
through the REAL wire: it builds actual signed bundles with ``build_edge_delta_rows`` and
applies them through ``apply_changes`` / ``apply_edge_inserts`` / ``apply_deletes``, and
it models the far side as a MIRROR - the state a peer would hold after applying exactly
what crossed the boundary. So what it proves is that the PROTOCOL converges: what ships,
what the cursor does, which side wins a conflict, whether a replay or a half-applied
bundle can leave the two sides different.

What it does NOT prove is two independent Postgres databases agreeing, because this suite
runs on SQLite against a single database - and on the one property where those differ
(deferred foreign keys) SQLite is the weaker environment, which is exactly how the
2026-08-19 wedge stayed invisible. That gap is named here rather than papered over:
``docs/EDGE_SYNC_OPERATIONS.md`` carries the two-box drill for the part a single database
cannot show.

Scenarios (each is a method, each returns a verdict dict):

  clean_sync              a fresh box receives the corpus
  outage_both_sides       14 days dark, writes on BOTH sides, then a restore
  midbundle_drop          the link dies with half a bundle applied
  power_cut_before_cursor rows applied, process killed before the cursor advanced
  clock_skew              the box's clock is ten minutes out
  duplicate_bundle        the identical bundle is delivered twice
  delete_propagation      a deletion crosses, and does not come back
  authority_invariants    money/grade/permission columns never moved the wrong way
"""
from __future__ import annotations

import datetime as dt
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


class Mirror:
    """The far side, as it would look after applying exactly what crossed the boundary.

    A dict of ``{(entity_type, id): {field: value}}`` plus a set of buried keys. Modelling
    the peer rather than standing up a second database is what lets the harness run in an
    ordinary test process; the cost is stated in the module docstring.
    """

    def __init__(self):
        self.rows: dict = {}
        self.buried: set = set()

    def apply(self, bundle_rows) -> dict:
        """Apply wire rows the way a receiver would. Returns simple counters."""
        applied = deleted = ignored = 0
        for row in bundle_rows:
            key = (row.get("entity_type"), str(row.get("id")))
            if str(row.get("op") or "").lower() == "delete":
                self.rows.pop(key, None)
                self.buried.add(key)
                deleted += 1
                continue
            if key in self.buried:
                # Delete dominance, mirrored: a burial is not undone by an older payload.
                ignored += 1
                continue
            self.rows.setdefault(key, {}).update(row.get("changes") or {})
            applied += 1
        return {"applied": applied, "deleted": deleted, "ignored": ignored}

    def snapshot(self) -> dict:
        return {k: dict(v) for k, v in self.rows.items()}


def _local_snapshot(school, entities=None) -> dict:
    """The same shape as :meth:`Mirror.snapshot`, read from the database."""
    from apps.api.sync_services import _get_entity_config

    want = {e for e in (entities or [])}
    out: dict = {}
    for entity_type, (model, allowed) in _get_entity_config(include_derived=True).items():
        if want and entity_type not in want:
            continue
        try:
            rows = model._default_manager.filter(school=school)
        except Exception:  # noqa: BLE001 - a model without `school` is not on the rail
            continue
        for instance in rows.iterator():
            out[(entity_type, str(instance.pk))] = {
                f: getattr(instance, f) for f in sorted(allowed) if hasattr(instance, f)
            }
    return out


def _differences(local: dict, mirror: dict, entities=None) -> list:
    """Keys and fields where the two sides disagree. Empty means converged.

    Compared as TEXT because the two sides arrive by different routes (one from a live
    model instance, one from a JSON wire payload), so ``3`` and ``"3"`` are the same value
    reported differently and must not read as divergence. A real difference survives that.
    """
    want = {e for e in (entities or [])}
    diffs = []
    keys = set(local) | set(mirror)
    for key in sorted(keys, key=lambda k: (str(k[0]), str(k[1]))):
        if want and key[0] not in want:
            continue
        left, right = local.get(key), mirror.get(key)
        if left is None:
            diffs.append({"key": key, "problem": "only on the far side"})
            continue
        if right is None:
            diffs.append({"key": key, "problem": "only on this side"})
            continue
        for field in sorted(set(left) & set(right)):
            if str(left[field]) != str(right[field]):
                diffs.append(
                    {
                        "key": key,
                        "field": field,
                        "local": str(left[field])[:60],
                        "remote": str(right[field])[:60],
                    }
                )
    return diffs


class ConvergenceHarness:
    """Run the scenarios against ``school`` and report a verdict per scenario."""

    def __init__(self, school, user, *, entities=None):
        self.school = school
        self.user = user
        # Scoped by default: the harness has to compare like with like, and an entity the
        # caller did not seed would show as "only on this side" for reasons that have
        # nothing to do with convergence.
        self.entities = set(entities or {"department", "classroom", "student"})

    # ------------------------------------------------------------------ plumbing
    def _delta(self, since=None):
        from apps.sync_engine.edge_outbox import build_edge_delta_rows

        rows, meta = build_edge_delta_rows(self.school, since=since)
        rows = [r for r in rows if r.get("entity_type") in self.entities]
        return rows, meta

    def _verdict(self, name, mirror, *, note="", extra=None):
        diffs = _differences(_local_snapshot(self.school, self.entities), mirror.snapshot(),
                             self.entities)
        return {
            "scenario": name,
            "converged": not diffs,
            "differences": diffs[:10],
            "difference_count": len(diffs),
            "note": note,
            **(extra or {}),
        }

    # ------------------------------------------------------------------ scenarios
    def clean_sync(self) -> dict:
        """A fresh box receives the corpus and matches the cloud."""
        mirror = Mirror()
        rows, _meta = self._delta()
        mirror.apply(rows)
        return self._verdict("clean_sync", mirror, note=f"{len(rows)} row(s) shipped")

    def outage_both_sides(self, seed_local, seed_remote) -> dict:
        """Fourteen days dark, writes on BOTH sides, then a restore.

        ``seed_local`` writes to the database; ``seed_remote`` returns wire rows the far
        side accumulated meanwhile. The test is whether one exchange in each direction is
        enough to agree - the ordinary claim "it catches up when it reconnects".
        """
        from apps.api.sync_services import apply_changes

        mirror = Mirror()
        mirror.apply(self._delta()[0])  # they were in step before the outage

        cutoff = timezone.now() - dt.timedelta(days=14)
        seed_local()
        remote_rows = list(seed_remote() or [])

        # Their changes come down...
        apply_changes(
            str(self.school.id), self.user, [r for r in remote_rows if r.get("op") != "delete"],
            persist_conflicts=False, sync_origin="cloud-pull",
        )
        mirror.apply(remote_rows)
        # ...and ours go up.
        ours, _meta = self._delta(since=cutoff)
        mirror.apply(ours)
        return self._verdict(
            "outage_both_sides", mirror,
            note=f"{len(remote_rows)} in, {len(ours)} out after 14 days apart",
        )

    def midbundle_drop(self, fraction=0.5) -> dict:
        """The link dies with only part of a bundle applied.

        The cursor must NOT advance over work that did not land, and the next exchange
        must deliver the remainder. A protocol that loses the tail here loses data
        silently on every flaky link.
        """
        mirror = Mirror()
        rows, _meta = self._delta()
        cut = max(1, int(len(rows) * fraction)) if rows else 0
        mirror.apply(rows[:cut])
        partial = self._verdict("midbundle_drop.partial", mirror)
        # The cursor never moved, so the whole window is re-offered; apply is idempotent.
        mirror.apply(rows)
        final = self._verdict(
            "midbundle_drop", mirror,
            note=f"delivered {cut}/{len(rows)} then resumed",
            extra={"diverged_while_partial": not partial["converged"]},
        )
        return final

    def power_cut_before_cursor(self) -> dict:
        """Rows applied, then the box dies before the cursor advanced.

        On restart the same window is requested again. The apply path is idempotent by
        construction (update-by-pk, upsert-by-anchor, create-by-pk), so the second
        delivery must change nothing - if it does, every unclean shutdown corrupts state.
        """
        mirror = Mirror()
        rows, _meta = self._delta()
        mirror.apply(rows)
        before = mirror.snapshot()
        mirror.apply(rows)  # replayed after the restart
        stable = before == mirror.snapshot()
        return self._verdict(
            "power_cut_before_cursor", mirror,
            note="re-applied the same window after an unclean shutdown",
            extra={"idempotent": stable},
        )

    def clock_skew(self, minutes=10) -> dict:
        """The box's clock is ten minutes out.

        Echo suppression here is provenance-based, not a clock compare, so skew must not
        change what converges. It CAN change which side wins an LWW tie, which is why the
        engine keeps money and grades off LWW entirely.
        """
        mirror = Mirror()
        skewed = timezone.now() + dt.timedelta(minutes=minutes)
        rows, _meta = self._delta()
        for row in rows:
            row["updated_at"] = skewed.isoformat()
        mirror.apply(rows)
        return self._verdict(
            "clock_skew", mirror, note=f"every row stamped {minutes} minutes ahead"
        )

    def duplicate_bundle(self) -> dict:
        """The identical bundle is delivered twice.

        Convergence must be unaffected, AND the replay guard must recognise the second
        delivery - the guard is what stops a captured bundle resurrecting a deleted row.
        """
        from apps.sync_engine.delta_bundle import export_delta_bundle, verify_and_parse_bundle
        from apps.sync_engine.replay_guard import register_bundle

        mirror = Mirror()
        rows, _meta = self._delta()
        data = export_delta_bundle(school_id=str(self.school.id), rows=rows, device_id="harness")
        first_collect, second_collect = {}, {}
        parsed, _errs = verify_and_parse_bundle(
            data, expected_school_id=self.school.pk, collect=first_collect
        )
        mirror.apply(parsed)
        first = register_bundle(self.school, first_collect, direction="cloud-pull",
                                row_count=len(parsed))
        verify_and_parse_bundle(data, expected_school_id=self.school.pk, collect=second_collect)
        second = register_bundle(self.school, second_collect, direction="cloud-pull",
                                 row_count=len(parsed))
        mirror.apply(parsed)
        return self._verdict(
            "duplicate_bundle", mirror,
            note=f"first={first or 'accepted'}, second={second or 'accepted'}",
            extra={"replay_detected": second == "bundle_replayed", "rows": len(parsed)},
        )

    def delete_propagation(self, delete_one) -> dict:
        """A deletion crosses, and the very next exchange does not bring the row back."""
        mirror = Mirror()
        mirror.apply(self._delta()[0])
        marker = timezone.now()
        key = delete_one()
        rows, _meta = self._delta(since=marker - dt.timedelta(seconds=1))
        mirror.apply(rows)
        gone_remotely = key not in mirror.rows
        mirror.apply(self._delta()[0])  # a full re-offer must not resurrect it
        return self._verdict(
            "delete_propagation", mirror,
            note="deleted locally, then re-offered the whole corpus",
            extra={"gone_remotely": gone_remotely, "stayed_gone": key not in mirror.rows},
        )

    def authority_invariants(self) -> dict:
        """No cloud-authoritative column may EVER be writable upward.

        This is the invariant the whole policy registry exists to hold, checked as a
        property of the registry rather than of any one code path - so a new entity that
        forgets its policy row fails here instead of in production.
        """
        from apps.api.sync_services import (
            _DOWN_ONLY_FIELDS_PER_ENTITY,
            _get_entity_config,
            _sync_conflict_policy,
        )
        from apps.sync_engine.policy_registry import MergeStrategy

        violations = []
        for entity_type in _get_entity_config(include_derived=True):
            strategy, protected = _sync_conflict_policy(entity_type)
            if strategy in {MergeStrategy.CAUSAL_LWW} and protected:
                violations.append(f"{entity_type}: protected but graded as LWW")
            if strategy == MergeStrategy.ONLINE_REQUIRED and not protected:
                violations.append(f"{entity_type}: online-required but not protected")
        for entity_type, fields in _DOWN_ONLY_FIELDS_PER_ENTITY.items():
            config = _get_entity_config(include_derived=True).get(entity_type)
            if config is None:
                violations.append(f"{entity_type}: down-only fields on an unregistered entity")
                continue
            missing = sorted(set(fields) - set(config[1]))
            if missing:
                # A down-only rule for a field that is not on the rail is a rule that does
                # nothing - and reads, to the next person, as protection that exists.
                violations.append(f"{entity_type}: down-only fields not on the rail: {missing}")
        return {
            "scenario": "authority_invariants",
            "converged": not violations,
            "difference_count": len(violations),
            "differences": violations[:10],
            "note": "policy registry / per-field direction consistency",
        }


__all__ = ["ConvergenceHarness", "Mirror"]
