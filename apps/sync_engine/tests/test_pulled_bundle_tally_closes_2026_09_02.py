"""A pulled bundle must account for every row it received (2026-09-02).

``apply_deletes`` answers 200 in THREE shapes and only one of them is a deletion::

    {"deleted": True}                             counted by ``deleted``
    {"deleted": False, "already_absent": True}    counted by nothing
    {"deleted": False, "soft_deleted": True}      counted by nothing

``tally_skipped_rows`` skips every 2xx by design -- a 200 is not a refusal -- so the last
two fell out of the summary entirely, and the summary is what the pull command prints.

MEASURED on the Gilead box 2026-09-02, on the real rail::

    SPLIT received=75755 updates=75709 inserts=0 deletes=46 malformed=0
    APPLY_DELETES in=46 results=46 deleted=0 statuses={200: 46}
    Pulled 75755 row(s) -> applied 75709, created 0, upserted 0, deleted 0,
                           conflicts 0, malformed 0, skipped 0.

Every one of those numbers is true and they sum to 75,709. Forty-six rows were reported
by nothing at all, and the output gave an operator no way to tell that from a clean sync.

WHY THAT IS WORTH TESTING. ``already_absent`` is the ordinary answer when both sides
already agree a row is gone. It is ALSO exactly what a deletion that hit the WRONG row
leaves behind on every cycle afterwards. Those two situations printed identically, and
one of them is data loss -- so a destructive bundle and a harmless one wore the same
shape, and nobody had to explain the shortfall because no bucket was missing; the
buckets simply did not have to add up.

WHAT THE 46 ACTUALLY WERE IS STILL UNMEASURED, and an earlier reading of this got it
wrong in a way worth recording HERE, in the file whose whole subject is arithmetic
nobody checked. That reading said 13 teacher records had been destroyed, by subtracting
26 survivors from 39 tombstones. The box's own data does not support it: live teacher
pks are 2..27 and the tombstones cover 28..66, which are DISJOINT, so ``already_absent``
may be literally true for all 39. It is not disproven either -- it is unmeasured. (The 6
``specialty_subject`` tombstones, pks 1..6, DO overlap where a small catalog's rows live,
and that has not been checked.) A subtraction that looked convincing is the same kind of
reasoning this module now refuses to accept from itself.

The tests here are about the arithmetic, not the deletion. Whether anything died is
somebody's bug to chase; the SILENCE was this module's.

The previous attempt at this (``9575fbeef``) added ``deleted`` and ``skipped`` to the
printed line and stated in its own comment that the tally now sums to ``received``. It
did not, and the test that was supposed to prove it stubbed ``deleted=46`` -- the number
that would have made it close -- so the claim passed CI and shipped. That fixture is
corrected in ``test_pull_inbox_reporting_2026_08_31.py`` in the same commit as this file.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.sync_engine.edge_inbox import (
    _apply_pulled_bundle_inner,
    tally_delete_outcomes,
    unaccounted_rows,
)

# The measured Gilead pull, to the row. Pinned as literals so a regression reads as the
# incident it was rather than as an arithmetic puzzle.
GILEAD_RECEIVED = 75755
GILEAD_UPDATES = 75709
GILEAD_DELETES = 46


def _delete_result(index, **data):
    return {"index": index, "status": 200, "data": data}


def _summary(**overrides):
    """A closed tally. Each test perturbs exactly one bucket."""
    base = {
        "received": 0, "malformed": 0, "applied": 0, "conflicts": 0,
        "created": 0, "upserted": 0, "deleted": 0,
        "already_absent": 0, "soft_deleted": 0, "skipped": 0,
    }
    base.update(overrides)
    return base


class _AppliesABundle:
    """Drive the REAL ``_apply_pulled_bundle_inner`` with the wire and the apply path stubbed.

    The seams are chosen so that what is under test is the accounting and nothing else:
    the signature check, the replay guard and all three apply functions are replaced, so a
    change to any of them can neither rescue nor break these tests. Deliberately no
    database -- a summary that does not add up is arithmetic, and giving it a School would
    only make the failure slower to reach.
    """

    school = SimpleNamespace(id="s-1", pk="s-1")
    user = SimpleNamespace(is_superuser=True, is_staff=True)

    def _apply(self, *, updates=0, deletes=(), update_results=None, conflicts=(),
               inserts=0, created=0, upserted=0, insert_results=None):
        rows = [{"entity_type": "teacher", "id": str(i)} for i in range(updates)]
        rows += [{"entity_type": "teacher", "id": "x%d" % i, "client_offline_id": "c%d" % i}
                 for i in range(inserts)]
        rows += [{"op": "delete", "entity_type": "teacher", "id": str(900 + i)}
                 for i in range(len(deletes))]

        out = {
            "results": update_results if update_results is not None
            else [{"index": i, "status": 200, "data": {}} for i in range(updates)],
            "conflicts": list(conflicts),
            "success_count": updates - len(conflicts),
        }
        ins = {
            "created": created,
            "updated": upserted,
            "results": insert_results if insert_results is not None
            else [{"index": i, "status": 201, "data": {}} for i in range(inserts)],
        }
        rem = {
            "deleted": sum(1 for d in deletes if (d.get("data") or {}).get("deleted")),
            "results": list(deletes),
        }

        with patch("apps.sync_engine.edge_inbox.verify_and_parse_bundle",
                   return_value=(rows, [])), \
             patch("apps.sync_engine.replay_guard.register_bundle", return_value=None), \
             patch("apps.api.sync_services._get_entity_config", return_value={}), \
             patch("apps.api.sync_services._insert_dependency_order", return_value=[]), \
             patch("apps.api.sync_services.apply_changes", return_value=out), \
             patch("apps.api.sync_services.apply_edge_inserts", return_value=ins), \
             patch("apps.api.sync_services.apply_deletes", return_value=rem):
            return _apply_pulled_bundle_inner(self.school, self.user, b"{}")


class EveryRowLandsInSomeBucketTests(_AppliesABundle, SimpleTestCase):
    """LOAD-BEARING. Each of these fails on the unfixed tree, on its own assertion."""

    def test_a_row_that_was_already_gone_is_counted(self):
        # The 46. `apply_deletes` answered 200 for every one of them and removed nothing,
        # so `deleted` stayed 0 and `skipped` stayed 0 and the rows were nowhere.
        deletes = [_delete_result(i, deleted=False, already_absent=True)
                   for i in range(GILEAD_DELETES)]
        summary = self._apply(updates=0, deletes=deletes)
        self.assertEqual(summary["already_absent"], GILEAD_DELETES)

    def test_a_row_the_model_soft_deleted_is_counted(self):
        # finance.Invoice keeps the row and marks it void, so `deleted` is 0 and the row
        # was never refused. That is a real outcome on this rail, counted by nothing.
        summary = self._apply(
            deletes=[_delete_result(0, deleted=False, soft_deleted=True)]
        )
        self.assertEqual(summary["soft_deleted"], 1)

    def test_the_measured_gilead_pull_now_closes(self):
        # The whole incident in one assertion: 75,755 received, 46 of them deletions that
        # removed nothing, and a tally that must not be 46 short.
        deletes = [_delete_result(i, deleted=False, already_absent=True)
                   for i in range(GILEAD_DELETES)]
        summary = self._apply(updates=GILEAD_UPDATES, deletes=deletes)
        self.assertEqual(summary["received"], GILEAD_RECEIVED)
        self.assertEqual(summary["applied"], GILEAD_UPDATES)
        self.assertEqual(summary["deleted"], 0)
        self.assertEqual(summary["unaccounted"], 0)

    def test_a_real_deletion_is_not_absorbed_into_the_new_bucket(self):
        # The counting must stay SPECIFIC. Sweeping every 200 into `already_absent`
        # would close the arithmetic and destroy the diagnosis at the same time: a
        # rail that removed rows and a rail that found none would read alike again,
        # which is the exact failure this whole change exists to end.
        summary = self._apply(deletes=[_delete_result(0, deleted=True)])
        self.assertEqual(summary["already_absent"], 0)
        self.assertEqual(summary["soft_deleted"], 0)
        self.assertEqual(summary["unaccounted"], 0)

    def test_a_refusal_is_not_absorbed_into_the_new_bucket_either(self):
        # A 409 is the shape a tombstone wears on the box RIGHT NOW, with propagation
        # disabled. Counting it as `already_absent` would dress a refused wipe up as a
        # routine no-op and quietly undo the containment.
        summary = self._apply(deletes=[
            {"index": 0, "status": 409,
             "data": {"error": "delete_propagation_disabled"}}
        ])
        self.assertEqual(summary["already_absent"], 0)
        self.assertEqual(summary["unaccounted"], 0)

    def test_a_pull_with_no_deletions_at_all_still_closes(self):
        summary = self._apply(updates=500)
        self.assertEqual(summary["unaccounted"], 0)

    def test_a_mixed_bundle_closes(self):
        summary = self._apply(
            updates=10, conflicts=[{"index": 9}], inserts=3, created=2, upserted=1,
            deletes=[_delete_result(0, deleted=True),
                     _delete_result(1, deleted=False, already_absent=True)],
        )
        self.assertEqual(summary["unaccounted"], 0)

    def test_a_shape_no_bucket_knows_is_reported_rather_than_lost(self):
        # The seal, and the reason this is not just two more keys. A 200 carrying neither
        # `deleted` nor `already_absent` nor `soft_deleted` is a shape that does not exist
        # today -- and the next one that does must announce itself instead of evaporating,
        # because evaporating silently is exactly what cost 13 records.
        summary = self._apply(deletes=[_delete_result(0, deleted=False)])
        self.assertEqual(summary["unaccounted"], 1)


class TheOtherBucketsStillMeanWhatTheyMeantTests(_AppliesABundle, SimpleTestCase):
    """CONTROLS. Every assertion here is on a bucket that existed BEFORE this change,
    so all of them pass on the unfixed tree as well -- which is the only thing that
    makes them controls rather than a second set of load-bearing tests.

    They guard the direction nobody watches: "make the tally close" can also be
    satisfied by quietly recounting something that was already correct, which would
    close the arithmetic and destroy the diagnosis in the same move.
    """

    def test_a_real_deletion_is_still_a_deletion(self):
        summary = self._apply(deletes=[_delete_result(0, deleted=True)])
        self.assertEqual(summary["deleted"], 1)

    def test_a_refused_delete_is_still_a_skip_with_its_reason(self):
        # 409 is a refusal and belongs to `skipped` with its reason intact. This is the
        # shape a tombstone wears on the box today, with propagation disabled, so it is
        # worth pinning independently of anything this change added.
        summary = self._apply(deletes=[
            {"index": 0, "status": 409,
             "data": {"error": "delete_propagation_disabled"}}
        ])
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(
            summary["skipped_reasons"], {"delete_propagation_disabled": 1}
        )

    def test_a_protected_delete_refusal_is_still_a_skip(self):
        summary = self._apply(deletes=[
            {"index": 0, "status": 409, "data": {"error": "delete_refused_protected"}}
        ])
        self.assertEqual(summary["skipped"], 1)

    def test_an_update_only_pull_reports_what_it_always_did(self):
        summary = self._apply(updates=500)
        self.assertEqual(summary["received"], 500)
        self.assertEqual(summary["applied"], 500)
        self.assertEqual(summary["skipped"], 0)

    def test_conflicts_and_inserts_keep_their_own_buckets(self):
        summary = self._apply(
            updates=10,
            conflicts=[{"index": 9}],
            inserts=3,
            created=2,
            upserted=1,
        )
        self.assertEqual(summary["applied"], 9)
        self.assertEqual(summary["conflicts"], 1)
        self.assertEqual(summary["created"], 2)
        self.assertEqual(summary["upserted"], 1)


class TheArithmeticItselfTests(SimpleTestCase):
    """The two helpers, without a bundle. Pure functions; pinned to the measured numbers."""

    def test_the_gilead_summary_was_short_by_exactly_forty_six(self):
        # What the box actually printed on 2026-09-02, run through the checker that did
        # not exist that day. 46 is the count of tombstones in that bundle.
        printed = _summary(received=GILEAD_RECEIVED, applied=GILEAD_UPDATES)
        self.assertEqual(unaccounted_rows(printed), GILEAD_DELETES)

    def test_the_same_summary_closes_once_the_bucket_exists(self):
        printed = _summary(received=GILEAD_RECEIVED, applied=GILEAD_UPDATES,
                           already_absent=GILEAD_DELETES)
        self.assertEqual(unaccounted_rows(printed), 0)

    def test_a_missing_key_is_treated_as_zero_not_as_a_crash(self):
        # A summary crossing a version boundary (an older apply path, a stubbed dict in a
        # sibling test) must still yield a number. A reporting check that raises would
        # turn an accounting bug into an outage, which is worse than the bug.
        self.assertEqual(unaccounted_rows({"received": 5, "applied": 5}), 0)

    def test_only_the_non_deleting_two_hundreds_are_counted(self):
        outcomes = tally_delete_outcomes([
            _delete_result(0, deleted=True),
            _delete_result(1, deleted=False, already_absent=True),
            _delete_result(2, deleted=False, soft_deleted=True),
            {"index": 3, "status": 409, "data": {"error": "delete_refused_protected"}},
            {"index": 4, "status": 422, "data": {"error": "delete_failed"}},
            {"index": 5, "status": 400, "data": {"error": "entity_type_and_id_required"}},
        ])
        self.assertEqual(outcomes, {"already_absent": 1, "soft_deleted": 1})

    def test_an_empty_result_list_counts_nothing(self):
        self.assertEqual(
            tally_delete_outcomes([]), {"already_absent": 0, "soft_deleted": 0}
        )
        self.assertEqual(
            tally_delete_outcomes(None), {"already_absent": 0, "soft_deleted": 0}
        )
