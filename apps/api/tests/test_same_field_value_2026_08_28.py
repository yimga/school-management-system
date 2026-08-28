"""A datetime and a JSON field were never equal to themselves across the wire.

The no-op check added on 2026-08-27 stopped the engine filing conflicts about rows
that had not changed. It cleared 67,491 of them on the Gilead box. But it compared
two values that had arrived by different routes with no idea what they were supposed
to be, so it could only be sure about plain scalars -- and two whole classes of rail
column fell through:

    wire datetime  '2026-08-21 19:12:54.708842+00:00'   json.dumps(default=str)
    local datetime '2026-08-21T19:12:54.708842+00:00'   isoformat()

one character apart, for the same instant; and a JSONField, whose value is a dict and
therefore not a scalar at all. MEASURED on 2026-08-28: 8 of the 17 rail entities carry
such a field. Every replay filed a fresh conflict about every one of those rows, about
values that were identical, and would have gone on doing so forever.

The engine already owned the answer. ``parity._canonical`` was written for the G8 seal,
where two deployments had to agree on what a value IS; it normalises datetimes to UTC
and recurses into dicts. It had only ever been pointed at local rows. Paired with
Django's own ``to_python``, which parses the wire form back into the column's type, both
sides become comparable -- and the direction of doubt does not move: every uncertainty
still resolves to "changed", and lets the write happen.

These round-trip through the REAL bundle rather than hand-typing the wire form, because
the defect was IN the wire form -- a test that typed its own strings would have agreed
with whatever the check already did.
"""
from __future__ import annotations

import datetime
import decimal
import uuid

from django.test import SimpleTestCase, TestCase

from apps.api.sync_services import (
    _get_entity_config,
    _same_field_value,
    _same_value,
)
from apps.sync_engine.delta_bundle import export_delta_bundle, verify_and_parse_bundle

UTC = datetime.timezone.utc


def _through_the_wire(values: dict) -> dict:
    """What the receiver actually gets, via the real signed bundle."""
    raw = export_delta_bundle(school_id="s", rows=[{"changes": values}], device_id="cloud")
    rows, errors = verify_and_parse_bundle(raw)
    assert not errors, errors
    return rows[0]["changes"]


class TheComparisonMustSurviveTheWireFormatTests(SimpleTestCase):
    """The three shapes that were broken, and proof the old check really broke them."""

    def setUp(self):
        cfg = _get_entity_config(include_derived=True)
        self.year_model = cfg["academic_year"][0]
        self.teacher_model = cfg["teacher"][0]
        self.student_model = cfg["student"][0]
        self.moment = datetime.datetime(2026, 8, 21, 19, 12, 54, 708842, tzinfo=UTC)
        self.attrs = {"a": 1, "b": [2, 3], "c": {"d": None}}
        self.wire = _through_the_wire(
            {
                "locked_at": self.moment,
                "custom_attributes": self.attrs,
                "classroom_id": 42,
            }
        )

    # -- the defect, and that the fixture still reproduces it -----------------

    def test_the_old_comparison_really_did_call_a_datetime_changed(self):
        # Without this the test below could pass on a fixture where nothing was ever
        # wrong, and would quietly stop meaning anything.
        self.assertFalse(_same_value(self.moment, self.wire["locked_at"]))

    def test_the_old_comparison_really_did_call_a_dict_changed(self):
        self.assertFalse(_same_value(self.attrs, self.wire["custom_attributes"]))

    # -- what it does now -----------------------------------------------------

    def test_the_same_instant_is_not_a_change(self):
        self.assertTrue(
            _same_field_value(
                self.year_model, "locked_at", self.moment, self.wire["locked_at"]
            )
        )

    def test_the_same_instant_in_another_offset_is_not_a_change(self):
        # A box on a local TIME_ZONE and a cloud on UTC describe one moment two ways.
        # This is the case parity._canonical was written for.
        elsewhere = self.moment.astimezone(datetime.timezone(datetime.timedelta(hours=1)))
        self.assertTrue(
            _same_field_value(
                self.year_model, "locked_at", elsewhere, self.wire["locked_at"]
            )
        )

    def test_the_same_dict_is_not_a_change(self):
        self.assertTrue(
            _same_field_value(
                self.teacher_model,
                "custom_attributes",
                self.attrs,
                self.wire["custom_attributes"],
            )
        )

    def test_a_dict_whose_keys_were_written_in_another_order_is_not_a_change(self):
        reordered = {"c": {"d": None}, "b": [2, 3], "a": 1}
        self.assertTrue(
            _same_field_value(
                self.teacher_model,
                "custom_attributes",
                reordered,
                self.wire["custom_attributes"],
            )
        )

    def test_a_foreign_key_id_is_not_a_change_because_of_its_type(self):
        self.assertTrue(
            _same_field_value(
                self.student_model, "classroom_id", 42, self.wire["classroom_id"]
            )
        )

    # -- and what it must still refuse to call equal --------------------------

    def test_a_different_instant_is_a_change(self):
        later = self.moment + datetime.timedelta(hours=1)
        self.assertFalse(
            _same_field_value(self.year_model, "locked_at", later, self.wire["locked_at"])
        )

    def test_a_difference_of_one_microsecond_is_a_change(self):
        near = self.moment + datetime.timedelta(microseconds=1)
        self.assertFalse(
            _same_field_value(self.year_model, "locked_at", near, self.wire["locked_at"])
        )

    def test_a_different_dict_is_a_change(self):
        self.assertFalse(
            _same_field_value(
                self.teacher_model, "custom_attributes", {"a": 2}, self.wire["custom_attributes"]
            )
        )

    def test_an_extra_key_is_a_change(self):
        richer = dict(self.attrs, extra=9)
        self.assertFalse(
            _same_field_value(
                self.teacher_model, "custom_attributes", richer, self.wire["custom_attributes"]
            )
        )

    def test_a_nested_difference_is_a_change(self):
        nested = {"a": 1, "b": [2, 4], "c": {"d": None}}
        self.assertFalse(
            _same_field_value(
                self.teacher_model, "custom_attributes", nested, self.wire["custom_attributes"]
            )
        )

    def test_a_different_foreign_key_id_is_a_change(self):
        self.assertFalse(
            _same_field_value(
                self.student_model, "classroom_id", 43, self.wire["classroom_id"]
            )
        )

    def test_absent_on_one_side_is_a_change(self):
        self.assertFalse(
            _same_field_value(self.year_model, "locked_at", None, self.wire["locked_at"])
        )

    # -- every failure path resolves to "changed" -----------------------------

    def test_a_column_this_model_does_not_have_is_a_change(self):
        # Never "these are equal because I could not look it up".
        self.assertFalse(
            _same_field_value(self.student_model, "no_such_column", {"a": 1}, {"a": 1})
        )

    def test_a_value_the_column_rejects_is_a_change(self):
        self.assertFalse(
            _same_field_value(self.year_model, "locked_at", self.moment, "not a datetime")
        )

    def test_a_many_to_many_is_never_reported_equal(self):
        # A manager stringifies to something a wire value can genuinely equal, and
        # skipping that write would turn a 422 into a green 200.
        m2m = [
            f.name
            for f in self.student_model._meta.get_fields()
            if getattr(f, "many_to_many", False)
        ]
        if not m2m:
            self.skipTest("this model has no many-to-many field to check")
        name = m2m[0]
        self.assertFalse(_same_field_value(self.student_model, name, object(), "anything"))


class EveryRailColumnMustBeComparableTests(SimpleTestCase):
    """Measured across the whole registry, not the three entities picked by hand.

    The defect was found in `academic_year` and `teacher`, but it belonged to a TYPE,
    not to an entity. Anything added to the rail tomorrow inherits this test.
    """

    #: One representative value per column type this can build. A type absent here is
    #: reported by the test below rather than silently passing.
    SAMPLES = {
        "DateTimeField": datetime.datetime(2026, 3, 4, 5, 6, 7, 890123, tzinfo=UTC),
        "DateField": datetime.date(2026, 3, 4),
        "TimeField": datetime.time(5, 6, 7),
        "DecimalField": decimal.Decimal("12.50"),
        "FloatField": 1.25,
        "IntegerField": 7,
        "PositiveIntegerField": 7,
        "PositiveSmallIntegerField": 7,
        "SmallIntegerField": 7,
        "BigIntegerField": 7,
        "BooleanField": True,
        "CharField": "value",
        "TextField": "value",
        "SlugField": "a-slug",
        "EmailField": "a@b.com",
        "UUIDField": uuid.UUID("12345678-1234-5678-1234-567812345678"),
        "JSONField": {"k": [1, 2], "z": None},
        "DurationField": datetime.timedelta(seconds=90),
    }

    def test_no_rail_column_is_unequal_to_itself_across_the_wire(self):
        cfg = _get_entity_config(include_derived=True)
        unequal = []
        checked = 0
        for entity_type, (model, allowed) in sorted(cfg.items()):
            for f in model._meta.get_fields():
                if not getattr(f, "concrete", False) or getattr(f, "many_to_many", False):
                    continue
                name = f.attname if f.attname in allowed else f.name
                if name not in allowed:
                    continue
                sample = self.SAMPLES.get(f.get_internal_type())
                if f.is_relation:
                    sample = 4242
                if sample is None:
                    continue
                wire = _through_the_wire({name: sample})[name]
                checked += 1
                if not _same_field_value(model, name, sample, wire):
                    unequal.append("%s.%s (%s)" % (entity_type, name, f.get_internal_type()))
        self.assertGreater(checked, 50, "the sweep found almost nothing to check")
        self.assertEqual(unequal, [], "rail columns unequal to themselves: %r" % unequal)

    def test_the_sample_table_covers_every_type_on_the_rail(self):
        # A type with no sample is not checked by the test above, and would hide the
        # next instance of this bug. Fail loudly rather than quietly skipping.
        cfg = _get_entity_config(include_derived=True)
        uncovered = set()
        for _entity_type, (model, allowed) in cfg.items():
            for f in model._meta.get_fields():
                if not getattr(f, "concrete", False) or getattr(f, "many_to_many", False):
                    continue
                if f.is_relation:
                    continue
                if f.attname not in allowed and f.name not in allowed:
                    continue
                if f.get_internal_type() not in self.SAMPLES:
                    uncovered.add(f.get_internal_type())
        self.assertEqual(
            sorted(uncovered), [], "rail column types with no sample value: add them"
        )


class ARowWithADatetimeMustLandRatherThanConflictTests(TestCase):
    """The whole point, exercised through the real apply path.

    ``academic_year`` carries four DateTimeFields on the rail. Before this change an
    identical row of it could not reach the no-op check as unchanged: ``locked_at``
    compared unequal to itself, so the row fell through to the timestamp grading -- which
    on a box is unwinnable, because the box's own ``updated_at`` is always the newer one.
    Every replay therefore filed a fresh conflict about a row that agreed in every field.
    """

    def setUp(self):
        from apps.accounts.models import User
        from apps.schools.models import School, SchoolMembership

        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Same {uid}", slug=f"same-{uid}", subdomain=f"same{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"same_{uid}", password="Test1234", email=f"s{uid}@t.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        model, allowed = _get_entity_config(include_derived=True)["academic_year"]
        # Asserted, not assumed: if locked_at ever leaves the rail this test would go on
        # passing while testing nothing at all.
        self.assertIn("locked_at", allowed)
        self.moment = datetime.datetime(2026, 8, 21, 19, 12, 54, 708842, tzinfo=UTC)
        self.year = model.objects.create(
            school=self.school,
            name=f"Year {uid}",
            start_date="2026-09-01",
            end_date="2027-07-31",
            locked_at=self.moment,
        )

    def _row(self, changes):
        # An OLDER stamp than the local row, which is the box's permanent condition:
        # its own apply bumped updated_at, so the cloud's copy is always the older one.
        return {
            "entity_type": "academic_year",
            "id": self.year.pk,
            "client_offline_id": "",
            "changes": changes,
            "updated_at": "2026-08-01T00:00:00+00:00",
        }

    def _apply(self, changes):
        from apps.api.sync_services import apply_changes

        return apply_changes(
            str(self.school.id), self.user, [self._row(changes)], sync_origin="cloud-pull"
        )

    def test_an_identical_datetime_does_not_manufacture_a_conflict(self):
        from apps.siteconfig.models import SyncConflict

        wire = _through_the_wire({"locked_at": self.moment, "name": self.year.name})
        out = self._apply(wire)

        self.assertEqual(out["conflicts"], [], out)
        self.assertEqual(SyncConflict.objects.filter(school=self.school).count(), 0)
        self.assertEqual(out["results"][0]["status"], 200, out)
        self.assertTrue(out["results"][0]["data"].get("unchanged"), out)

    def test_the_row_is_not_rewritten_so_its_stamp_does_not_move(self):
        # Landing a no-op by SAVING it would bump updated_at and re-enter the row into
        # the next delta going the other way: churn manufactured by the fix for churn.
        model = _get_entity_config(include_derived=True)["academic_year"][0]
        before = model.objects.get(pk=self.year.pk).updated_at
        self._apply(_through_the_wire({"locked_at": self.moment, "name": self.year.name}))
        self.assertEqual(model.objects.get(pk=self.year.pk).updated_at, before)

    def test_a_genuinely_changed_datetime_is_still_not_swallowed(self):
        # The fix must not have bought quiet by dropping real changes. A different
        # instant has to reach the engine's normal decision, not be waved through as a
        # no-op.
        from apps.siteconfig.models import SyncConflict

        later = self.moment + datetime.timedelta(hours=3)
        out = self._apply(_through_the_wire({"locked_at": later, "name": self.year.name}))

        unchanged = out["results"][0]["data"].get("unchanged") if out["results"] else None
        self.assertFalse(
            unchanged,
            "a real change was reported as a no-op: %r" % (out["results"],),
        )
        model = _get_entity_config(include_derived=True)["academic_year"][0]
        row = model.objects.get(pk=self.year.pk)
        decided = bool(out["conflicts"]) or SyncConflict.objects.filter(
            school=self.school
        ).exists()
        self.assertTrue(
            decided or row.locked_at == later,
            "the change neither landed nor was adjudicated: %r" % (out,),
        )
