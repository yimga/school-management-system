"""It does not take the whole corpus to fetch one table.

A ``missing_reference`` means a child arrived whose parent this box does not have. The
healing move was to rewind the pull cursor to "no position", so the next cycle
re-downloaded every row of every entity -- 315,964 of them on the Gilead box -- to
collect one absent parent. And a full-corpus pull re-offers every row the box already
holds, so the replay was itself what drove waves of conflict and skip records through
the apply path. The cure was the disease.

The engine already had the right move and was using it elsewhere. G8's
``_flush_drifted_entities`` re-pulls ONE ENTITY whole, over the ordinary rail, and
leaves the cursor alone -- its own docstring says rewinding "replays the ENTIRE corpus
to repair one table, which on a metered link is a bill and on a large school is an
hour". The parent labels have ridden through the inbox since 2026-08-27 and were only
being used to decide WHETHER to rewind. They are enough to say WHICH TABLE.

These assert on what was actually REQUESTED, not on the note, because a note is easy to
write and the whole defect was a request that was too big.
"""
from __future__ import annotations

import uuid
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.schools.models import School
from apps.sync_engine.models import EdgeSyncCursor, set_sync_cursor
from apps.sync_engine.sync_runner import (
    _rail_entity_by_model_label,
    _rail_model_labels,
    _request_replay_for_missing_parents,
)

_PULL = "apps.sync_engine.edge_outbox.pull_bundle"
_APPLY = "apps.sync_engine.edge_inbox.apply_pulled_bundle"
_LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

OFF_RAIL = "finance.ComplianceProfile"


class TheLabelToEntityMapMustComeFromTheRegistryTests(TestCase):
    def test_it_maps_a_rail_model_to_the_entity_type_that_fetches_it(self):
        by_label = _rail_entity_by_model_label()
        self.assertEqual(by_label.get("academics.Subject"), "subject")
        self.assertEqual(by_label.get("people.StudentProfile"), "student")

    def test_it_knows_exactly_the_models_the_rail_carries(self):
        # Same source as _rail_model_labels, so a new entity becomes repairable the day
        # it is added with nothing here to remember.
        self.assertEqual(set(_rail_entity_by_model_label()), _rail_model_labels())

    def test_it_does_not_claim_an_off_rail_model(self):
        self.assertNotIn(OFF_RAIL, _rail_entity_by_model_label())


@override_settings(CACHES=_LOCMEM)
class TheRepairMustAskForOneTableTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Repair {uid}",
            slug=f"repair-{uid}",
            subdomain=f"repair{uid}",
            is_active=True,
        )
        set_sync_cursor(self.school, EdgeSyncCursor.PULL, "2026-08-01T00:00:00+00:00")
        # Read it BACK rather than remembering what was written: the column stores a
        # datetime, so comparing against the ISO string asserts about the setter's
        # argument instead of about the cursor.
        self.start = self._cursor()
        self.assertIsNotNone(self.start)
        by_label = _rail_entity_by_model_label()
        # Resolved from the live registry rather than typed here: a test that hardcodes
        # the pairing would keep passing after the registry stopped agreeing with it.
        self.subject_label = "academics.Subject"
        self.student_label = "people.StudentProfile"
        self.subject_entity = by_label[self.subject_label]
        self.student_entity = by_label[self.student_label]

    def _cursor(self):
        return (
            EdgeSyncCursor.objects.filter(school=self.school, direction=EdgeSyncCursor.PULL)
            .values_list("high_water", flat=True)
            .first()
        )

    def _repair(self, parents, *, applied=None, status=200):
        """Run the real function with the means to ask, and report what it asked for."""
        pull = mock.Mock(return_value=(status, b"", None))
        apply_fn = mock.Mock(
            return_value=applied if applied is not None else {"ok": True, "created": 1, "upserted": 0}
        )
        with mock.patch(_PULL, pull), mock.patch(_APPLY, apply_fn):
            note = _request_replay_for_missing_parents(
                self.school,
                parents,
                endpoint="https://hub.test/pull",
                token="tok",
                user=object(),
            )
        asked = [c.kwargs.get("entities") for c in pull.call_args_list]
        return note, [e for group in asked if group for e in group], pull

    # -- the point of the whole change ---------------------------------------

    def test_an_on_rail_parent_asks_for_that_entity_and_nothing_else(self):
        _note, asked, pull = self._repair({self.subject_label: 7})
        self.assertEqual(asked, [self.subject_entity])
        self.assertEqual(pull.call_count, 1)

    def test_the_pull_cursor_is_left_exactly_where_it_was(self):
        # The defect in one assertion: rewinding is what re-shipped the corpus.
        self._repair({self.subject_label: 7})
        self.assertEqual(self._cursor(), self.start)

    def test_the_request_asks_for_the_whole_table_not_a_delta(self):
        # since=None is what makes it able to carry a parent that sits behind the
        # cursor -- which is the entire reason the parent was missing.
        _note, _asked, pull = self._repair({self.subject_label: 1})
        self.assertIsNone(pull.call_args_list[0].kwargs.get("since"))

    def test_two_missing_parents_ask_for_both_tables(self):
        _note, asked, _pull = self._repair(
            {self.subject_label: 2, self.student_label: 3}
        )
        self.assertEqual(sorted(asked), sorted([self.subject_entity, self.student_entity]))

    # -- what it must still refuse to do -------------------------------------

    def test_an_off_rail_parent_is_named_and_never_requested(self):
        note, asked, pull = self._repair({OFF_RAIL: 4})
        self.assertEqual(asked, [])
        self.assertEqual(pull.call_count, 0)
        self.assertIn(OFF_RAIL, note)
        self.assertEqual(self._cursor(), self.start)

    def test_a_mixed_bundle_asks_for_what_it_can_and_names_what_it_cannot(self):
        note, asked, _pull = self._repair({self.subject_label: 2, OFF_RAIL: 5})
        self.assertEqual(asked, [self.subject_entity])
        self.assertIn(OFF_RAIL, note)
        self.assertIn("no request will produce it", note)
        self.assertEqual(self._cursor(), self.start)

    def test_without_a_way_to_ask_it_still_falls_back_to_the_rewind(self):
        # A caller that cannot do better must not be silently downgraded to doing
        # nothing -- that would turn an unknown into a decision.
        note = _request_replay_for_missing_parents(self.school, {self.subject_label: 1})
        self.assertIsNone(self._cursor())
        self.assertIn("replays the full corpus", note)

    # -- the cooldown is per ENTITY, which is the point ----------------------

    def test_the_same_table_is_not_requested_twice_in_a_cooldown(self):
        self._repair({self.subject_label: 1})
        note, asked, pull = self._repair({self.subject_label: 1})
        self.assertEqual(pull.call_count, 0)
        self.assertEqual(asked, [])
        self.assertIn("requested recently", note)

    def test_one_tables_cooldown_does_not_block_another(self):
        # Per school, a department that cannot be repaired would have silenced a
        # classroom that could -- for the whole cooldown, every cooldown.
        self._repair({self.subject_label: 1})
        _note, asked, pull = self._repair({self.student_label: 1})
        self.assertEqual(asked, [self.student_entity])
        self.assertEqual(pull.call_count, 1)

    # -- and it reports honestly ---------------------------------------------

    def test_a_repair_that_failed_says_so(self):
        note, _asked, _pull = self._repair({self.subject_label: 1}, status=503)
        self.assertIn("could NOT repair", note)
        self.assertIn(self.subject_entity, note)

    def test_a_repair_the_apply_refused_says_so(self):
        note, _asked, _pull = self._repair(
            {self.subject_label: 1}, applied={"ok": False, "errors": ["policy"]}
        )
        self.assertIn("could NOT repair", note)

    def test_a_successful_repair_says_what_it_landed(self):
        note, _asked, _pull = self._repair(
            {self.subject_label: 1}, applied={"ok": True, "created": 4, "upserted": 2}
        )
        self.assertIn(self.subject_entity, note)
        self.assertIn("4 created", note)

    def test_it_still_never_raises(self):
        class _Exploding:
            @property
            def pk(self):
                raise RuntimeError("boom")

        note = _request_replay_for_missing_parents(
            _Exploding(), {self.subject_label: 1},
            endpoint="https://hub.test/pull", token="t", user=object(),
        )
        self.assertIn("could not request a replay", note)
