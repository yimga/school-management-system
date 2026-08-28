"""A full-corpus replay must not be requested for a parent no replay can produce.

WHAT THE RUNNER DID. Any ``missing_reference`` in an applied bundle rewound the PULL
cursor to "no position", so the next cycle re-downloaded the entire corpus. That is the
right move when the absent parent RIDES THE RAIL -- it is missing only because its own
``updated_at`` sits behind the cursor, and a replay really does deliver it.

It is the wrong move when the parent's table does not ride at all. A replay cannot carry a
row the rail never carries, so the reference is still unresolvable next cycle and every
cycle after it, and the price of learning that is re-downloading everything, once per
cooldown, indefinitely. Worse than wasted: a full-corpus pull re-offers every row the box
already holds, which is what drove waves of avoidable conflict and skip records through
the apply path.

The runner could not tell the two apart because the inbox threw the evidence away --
``_tally`` kept ``{"missing_reference": 7}`` and dropped the model label the 409 was
carrying. So the label now rides through, and the decision is made on it.
"""
from __future__ import annotations

import uuid

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.schools.models import School
from apps.sync_engine.models import EdgeSyncCursor, set_sync_cursor
from apps.sync_engine.sync_runner import (
    _rail_model_labels,
    _request_replay_for_missing_parents,
)

# A model that rides (a replay WOULD deliver it) and one that does not (no replay ever
# will). Both resolved from the live registry in the tests below rather than trusted here.
ON_RAIL = "academics.Subject"
OFF_RAIL = "finance.ComplianceProfile"

_LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


class TheRailRegistryMustAnswerTheQuestionAskedTests(TestCase):
    def test_it_lists_what_the_rail_carries(self):
        labels = _rail_model_labels()
        self.assertIn(ON_RAIL, labels)
        self.assertIn("people.StudentProfile", labels)

    def test_it_excludes_a_model_the_rail_does_not_carry(self):
        self.assertNotIn(OFF_RAIL, _rail_model_labels())

    def test_it_is_derived_from_the_registry_not_a_list(self):
        # An entity added to the rail must become replayable the day it is added, with
        # nothing here to remember.
        from apps.api.sync_services import _get_entity_config

        expected = {
            model._meta.label
            for model, _allowed in _get_entity_config(include_derived=True).values()
        }
        self.assertEqual(_rail_model_labels(), expected)


@override_settings(CACHES=_LOCMEM)
class TheRewindMustDependOnWhetherItCanHelpTests(TestCase):
    def setUp(self):
        cache.clear()
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Replay {uid}", slug=f"replay-{uid}", subdomain=f"replay{uid}", is_active=True
        )
        set_sync_cursor(self.school, EdgeSyncCursor.PULL, "2026-08-01T00:00:00+00:00")

    def _cursor(self):
        return (
            EdgeSyncCursor.objects.filter(
                school=self.school, direction=EdgeSyncCursor.PULL
            )
            .values_list("high_water", flat=True)
            .first()
        )

    def test_an_off_rail_parent_leaves_the_cursor_alone(self):
        before = self._cursor()
        note = _request_replay_for_missing_parents(self.school, {OFF_RAIL: 12})

        self.assertEqual(self._cursor(), before, "the corpus must not be re-requested")
        self.assertIn(OFF_RAIL, note)
        self.assertIn("rail does not carry", note)

    def test_an_off_rail_parent_does_not_even_burn_the_cooldown(self):
        # If it consumed the cooldown, a genuine on-rail miss in the same window would be
        # silently declined for six hours.
        _request_replay_for_missing_parents(self.school, {OFF_RAIL: 1})
        _request_replay_for_missing_parents(self.school, {ON_RAIL: 1})
        self.assertIsNone(self._cursor())

    def test_an_on_rail_parent_still_rewinds(self):
        note = _request_replay_for_missing_parents(self.school, {ON_RAIL: 3})
        self.assertIsNone(self._cursor(), "rewound to no position")
        self.assertIn("replays the full corpus", note)

    def test_a_mixed_bundle_rewinds_and_says_what_it_cannot_repair(self):
        # A replay helps SOME of them, so the rewind stands -- but reporting only that
        # would present a partial repair as a complete one.
        note = _request_replay_for_missing_parents(
            self.school, {ON_RAIL: 2, OFF_RAIL: 5}
        )
        self.assertIsNone(self._cursor())
        self.assertIn("replays the full corpus", note)
        self.assertIn(OFF_RAIL, note)
        self.assertIn("no replay will produce it", note)

    def test_no_evidence_keeps_the_historical_behaviour(self):
        # A caller that cannot say which parent is missing must not be silently downgraded
        # to doing nothing -- that would turn an unknown into a decision.
        _request_replay_for_missing_parents(self.school)
        self.assertIsNone(self._cursor())

    def test_the_cooldown_still_applies_to_an_on_rail_miss(self):
        _request_replay_for_missing_parents(self.school, {ON_RAIL: 1})
        set_sync_cursor(self.school, EdgeSyncCursor.PULL, "2026-08-02T00:00:00+00:00")
        note = _request_replay_for_missing_parents(self.school, {ON_RAIL: 1})
        self.assertIsNotNone(self._cursor(), "second rewind declined")
        self.assertIn("replay was requested recently", note)

    def test_an_unknown_label_is_treated_as_unreachable(self):
        # A label the registry does not know cannot be produced by a replay either, and
        # guessing otherwise would restore the loop for exactly the unknown cases.
        note = _request_replay_for_missing_parents(self.school, {"nowhere.Model": 1})
        self.assertIsNotNone(self._cursor())
        self.assertIn("nowhere.Model", note)

    def test_it_never_raises(self):
        # A healing step must not be the thing that breaks a sync cycle.
        class _Exploding:
            @property
            def pk(self):
                raise RuntimeError("boom")

        note = _request_replay_for_missing_parents(_Exploding(), {ON_RAIL: 1})
        self.assertIn("could not request a replay", note)


class TheInboxMustCarryTheParentLabelTests(TestCase):
    """Without this the runner has nothing to decide on and the fix above is unreachable."""

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Inbox {uid}", slug=f"inbox-{uid}", subdomain=f"inbox{uid}", is_active=True
        )

    def test_a_missing_reference_result_keeps_the_model_label(self):
        from apps.academics.models import AcademicYear, Department
        from apps.accounts.models import User
        from apps.schools.models import SchoolMembership
        from apps.sync_engine.delta_bundle import export_delta_bundle
        from apps.sync_engine.edge_inbox import apply_pulled_bundle

        uid = uuid.uuid4().hex[:8]
        user = User.objects.create_superuser(
            username=f"inbox_{uid}", password="Test1234", email=f"i{uid}@t.com"
        )
        SchoolMembership.objects.create(
            user=user, school=self.school, role="ADMIN", is_primary=True
        )
        dept = Department.objects.create(
            school=self.school, name="Arts", code=f"ART-{uid}"
        )
        # Every OTHER reference on the row must resolve. _unresolvable_fk reports the
        # FIRST miss it finds, so a row with two dangling parents would pin whichever the
        # field order happened to reach -- and the test would be about iteration order.
        year = AcademicYear.objects.create(
            school=self.school, name=f"Year {uid}",
            start_date="2026-09-01", end_date="2027-07-31",
        )
        # A classroom pointing at a department that does not exist: the child cannot be
        # created, and the refusal must name academics.Department.
        rows = [
            {
                "entity_type": "classroom",
                "id": 987654,
                "client_offline_id": "",
                "changes": {
                    "name": "Ghost",
                    "code": f"G-{uid}",
                    "department_id": 999999,
                    "academic_year_id": year.pk,
                },
                "updated_at": "2026-08-01T00:00:00+00:00",
            }
        ]
        data = export_delta_bundle(
            school_id=str(self.school.id), rows=rows, device_id="cloud"
        )
        result = apply_pulled_bundle(self.school, user, data, origin="cloud-pull")

        self.assertTrue(result["ok"], result)
        self.assertIn("skipped_missing_parents", result)
        self.assertEqual(result["skipped_reasons"].get("missing_reference"), 1, result)
        self.assertEqual(
            result["skipped_missing_parents"], {"academics.Department": 1}, result
        )
        # The fixture is real, not accidentally empty: a department DOES exist for this
        # school, so the refusal is about the id the row named, not about an empty table.
        self.assertTrue(Department.objects.filter(pk=dept.pk).exists())

    def test_the_key_is_present_even_when_nothing_was_skipped(self):
        from apps.accounts.models import User
        from apps.schools.models import SchoolMembership
        from apps.sync_engine.delta_bundle import export_delta_bundle
        from apps.sync_engine.edge_inbox import apply_pulled_bundle

        uid = uuid.uuid4().hex[:8]
        user = User.objects.create_superuser(
            username=f"clean_{uid}", password="Test1234", email=f"c{uid}@t.com"
        )
        SchoolMembership.objects.create(
            user=user, school=self.school, role="ADMIN", is_primary=True
        )
        data = export_delta_bundle(
            school_id=str(self.school.id), rows=[], device_id="cloud"
        )
        result = apply_pulled_bundle(self.school, user, data, origin="cloud-pull")
        self.assertEqual(result["skipped_missing_parents"], {})
