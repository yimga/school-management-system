"""M10 -- double-booking prevention, both halves, honestly separated.

The guarantee has two independent halves and they are provable in different
places. This module states plainly which is which.

**Half 1 -- the DB backstop (Postgres-only by definition).** ``ExclusionConstraint``
is a Postgres ``EXCLUDE ... USING GIST`` clause; SQLite has no such thing and
never will, so the SQLite lane can NEVER observe it firing. What the SQLite lane
CAN prove -- and what nothing proved before -- is that the constraint is present
in the **migrated state**, i.e. in what actually gets applied to a Postgres
database, with the right expressions and the right partial condition, and that
it has not DRIFTED from the model. The realistic failure here is not "Postgres
stopped working"; it is an engineer editing ``Meta.constraints`` and not writing
the migration, so production keeps enforcing the OLD rule while the model file
says otherwise. Constraint state is read out of the migration graph via
``MigrationLoader``, never out of the source text.

**Half 2 -- the application guarantee (backend-agnostic, fully proven here).**
``create_resource_booking`` refuses an overlapping booking before the DB is ever
asked, and that refusal must leave NO row behind. The existing suite asserts the
exception; it never asserted the absence of the row, and it never pinned the
half-open interval boundary -- back-to-back bookings (one ends exactly when the
next begins) must be ALLOWED, and an off-by-one there silently blocks every
consecutive period in a school day.

What is NOT proven here, stated for the record: that a real Postgres instance
rejects a concurrent overlapping insert. That needs the ``postgres_booking``
lane (see ``test_resource_booking.py``), which does not run on SQLite.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields.ranges import RangeOperators
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.models import F, Q
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.schoolops.booking_services import (
    BookingConflictError,
    create_resource_booking,
    overlapping_confirmed_count,
)
from apps.schoolops.models import BookableResource, ResourceBooking
from apps.schools.models import School

User = get_user_model()


def _migrated_constraints(app_label: str, model_name: str) -> list:
    """Constraints as the MIGRATIONS define them -- what Postgres actually gets.

    Deliberately not ``Model._meta.constraints``: the model file is the thing
    that can silently disagree with the database.
    """
    loader = MigrationLoader(None, ignore_no_migrations=True)
    state = loader.project_state()
    model_state = state.models[(app_label, model_name)]
    return list(model_state.options.get("constraints", []))


class ExclusionConstraintIsInTheMigratedStateTests(SimpleTestCase):
    """Half 1: the Postgres backstop is real, correct, and not drifted."""

    def test_resource_booking_overlap_constraint_is_migrated(self):
        constraints = _migrated_constraints("schoolops", "resourcebooking")
        by_name = {c.name: c for c in constraints}
        self.assertIn(
            "exclude_overlapping_resource_bookings",
            by_name,
            msg=(
                "the overlap ExclusionConstraint is absent from the migrated "
                f"state; migrations carry only {sorted(by_name)}"
            ),
        )
        constraint = by_name["exclude_overlapping_resource_bookings"]
        self.assertIsInstance(constraint, ExclusionConstraint)

        # The exact rule Postgres will enforce: same school AND same resource AND
        # overlapping time. Any one of these degrading (e.g. EQUAL -> OVERLAPS on
        # a scalar, or a dropped resource_id term) silently widens or destroys the
        # guarantee while the constraint still "exists".
        self.assertEqual(
            list(constraint.expressions),
            [
                (F("school_id"), RangeOperators.EQUAL),
                (F("resource_id"), RangeOperators.EQUAL),
                (F("time_range"), RangeOperators.OVERLAPS),
            ],
        )
        self.assertEqual(RangeOperators.OVERLAPS, "&&")

        # Partial: only CONFIRMED and EXCLUSIVE (capacity==1) rows are indexed.
        # Dropping ``enforce_exclusive`` would break every capacity>1 resource;
        # dropping ``status`` would make a cancelled booking hold the slot.
        self.assertEqual(
            constraint.condition,
            Q(status="confirmed", enforce_exclusive=True),
        )

    def test_athletics_venue_overlap_constraint_is_migrated(self):
        constraints = _migrated_constraints("athletics", "fixturevenuebooking")
        by_name = {c.name: c for c in constraints}
        self.assertIn("exclude_overlapping_athletics_venue_bookings", by_name)
        constraint = by_name["exclude_overlapping_athletics_venue_bookings"]
        self.assertIsInstance(constraint, ExclusionConstraint)
        self.assertEqual(
            list(constraint.expressions),
            [
                (F("school_id"), RangeOperators.EQUAL),
                (F("venue_id"), RangeOperators.EQUAL),
                (F("time_range"), RangeOperators.OVERLAPS),
            ],
        )
        self.assertEqual(constraint.condition, Q(status="confirmed"))

    def test_migrated_constraints_have_not_drifted_from_the_models(self):
        """Model file and migration graph must agree, or production enforces the
        old rule while the code review reads the new one."""
        for app_label, model_name, model in (
            ("schoolops", "resourcebooking", ResourceBooking),
            (
                "athletics",
                "fixturevenuebooking",
                __import__(
                    "apps.athletics.models", fromlist=["FixtureVenueBooking"]
                ).FixtureVenueBooking,
            ),
        ):
            with self.subTest(model=model_name):
                migrated = {c.name: c for c in _migrated_constraints(app_label, model_name)}
                declared = {c.name: c for c in model._meta.constraints}
                self.assertEqual(
                    sorted(migrated),
                    sorted(declared),
                    msg=f"{app_label}.{model_name}: constraint NAMES drifted",
                )
                for name, declared_constraint in declared.items():
                    self.assertEqual(
                        migrated[name],
                        declared_constraint,
                        msg=(
                            f"{app_label}.{model_name}.{name} differs between the "
                            "migration graph and the model -- an unmigrated edit"
                        ),
                    )


class _BookingFixtureMixin:
    """Seeds genuine CONFIRMED rows. ``DateTimeRangeField``'s ORM write path is
    Postgres-only, so seeded rows go in raw with the canonical range literal --
    exactly what Postgres stores and what ``_range_bounds`` parses back."""

    def _seed_confirmed(self, resource, start, end, *, title="seed", status="confirmed"):
        start = start if timezone.is_aware(start) else timezone.make_aware(start)
        end = end if timezone.is_aware(end) else timezone.make_aware(end)
        now = timezone.now().isoformat()
        with connection.cursor() as cur:
            cur.execute(
                "INSERT INTO schoolops_resourcebooking "
                "(school_id, resource_id, title, time_range, status, "
                "enforce_exclusive, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                [
                    resource.school_id.hex
                    if hasattr(resource.school_id, "hex")
                    else resource.school_id,
                    resource.id,
                    title,
                    f"[{start.isoformat()},{end.isoformat()})",
                    status,
                    resource.capacity == 1,
                    now,
                    now,
                ],
            )


class OverlapDetectionBoundaryTests(_BookingFixtureMixin, TestCase):
    """Half 2a: the overlap predicate itself, at its edges.

    ``overlapping_confirmed_count`` is the whole application guarantee on any
    backend where the exclusion constraint cannot run, and on Postgres it is the
    friendly refusal that keeps users off an IntegrityError. Its interval maths
    was never pinned.
    """

    def setUp(self):
        self.school = School.objects.create(
            name="M10 Boundary School",
            slug=f"m10b-{uuid.uuid4().hex[:8]}",
            subdomain=f"m10b-{uuid.uuid4().hex[:8]}",
        )
        self.resource = BookableResource.objects.create(
            school=self.school, name="Lab A", capacity=1
        )
        self.base = timezone.now().replace(minute=0, second=0, microsecond=0)

    def test_back_to_back_bookings_do_not_overlap(self):
        """[09:00,10:00) then [10:00,11:00) is the normal school day."""
        self._seed_confirmed(self.resource, self.base, self.base + timedelta(hours=1))
        self.assertEqual(
            overlapping_confirmed_count(
                resource=self.resource,
                start=self.base + timedelta(hours=1),
                end=self.base + timedelta(hours=2),
            ),
            0,
        )

    def test_a_one_second_overlap_is_detected(self):
        self._seed_confirmed(self.resource, self.base, self.base + timedelta(hours=1))
        self.assertEqual(
            overlapping_confirmed_count(
                resource=self.resource,
                start=self.base + timedelta(minutes=59, seconds=59),
                end=self.base + timedelta(hours=2),
            ),
            1,
        )

    def test_a_fully_enclosed_booking_is_detected(self):
        self._seed_confirmed(self.resource, self.base, self.base + timedelta(hours=3))
        self.assertEqual(
            overlapping_confirmed_count(
                resource=self.resource,
                start=self.base + timedelta(hours=1),
                end=self.base + timedelta(hours=2),
            ),
            1,
        )

    def test_an_enclosing_booking_is_detected(self):
        self._seed_confirmed(
            self.resource,
            self.base + timedelta(hours=1),
            self.base + timedelta(hours=2),
        )
        self.assertEqual(
            overlapping_confirmed_count(
                resource=self.resource,
                start=self.base,
                end=self.base + timedelta(hours=3),
            ),
            1,
        )

    def test_a_cancelled_booking_does_not_hold_the_slot(self):
        self._seed_confirmed(
            self.resource,
            self.base,
            self.base + timedelta(hours=1),
            status="cancelled",
        )
        self.assertEqual(
            overlapping_confirmed_count(
                resource=self.resource, start=self.base, end=self.base + timedelta(hours=1)
            ),
            0,
        )

    def test_another_resource_does_not_hold_the_slot(self):
        other = BookableResource.objects.create(
            school=self.school, name="Lab B", capacity=1
        )
        self._seed_confirmed(other, self.base, self.base + timedelta(hours=1))
        self.assertEqual(
            overlapping_confirmed_count(
                resource=self.resource, start=self.base, end=self.base + timedelta(hours=1)
            ),
            0,
        )
        # ...and the seeded row IS counted against its own resource, so the zero
        # above is a real negative and not an empty fixture.
        self.assertEqual(
            overlapping_confirmed_count(
                resource=other, start=self.base, end=self.base + timedelta(hours=1)
            ),
            1,
        )

    def test_another_school_does_not_hold_the_slot(self):
        other_school = School.objects.create(
            name="M10 Other",
            slug=f"m10o-{uuid.uuid4().hex[:8]}",
            subdomain=f"m10o-{uuid.uuid4().hex[:8]}",
        )
        foreign = BookableResource.objects.create(
            school=other_school, name="Lab A", capacity=1
        )
        self._seed_confirmed(foreign, self.base, self.base + timedelta(hours=1))
        self.assertEqual(
            overlapping_confirmed_count(
                resource=self.resource, start=self.base, end=self.base + timedelta(hours=1)
            ),
            0,
        )


class DoubleBookingRefusalLeavesNoRowTests(_BookingFixtureMixin, TestCase):
    """Half 2b: the refusal is clean -- an exception AND no persisted row."""

    def setUp(self):
        self.school = School.objects.create(
            name="M10 Refusal School",
            slug=f"m10r-{uuid.uuid4().hex[:8]}",
            subdomain=f"m10r-{uuid.uuid4().hex[:8]}",
        )
        self.user = User.objects.create_user(
            username=f"m10-{uuid.uuid4().hex[:8]}",
            email="m10@test.local",
            password="x",
            role=User.Role.ADMIN,
        )
        self.resource = BookableResource.objects.create(
            school=self.school, name="Hall", capacity=1
        )
        self.base = timezone.now().replace(minute=0, second=0, microsecond=0)

    def test_refused_double_booking_creates_no_row(self):
        self._seed_confirmed(
            self.resource, self.base, self.base + timedelta(hours=2), title="Held"
        )
        before = ResourceBooking.objects.filter(resource=self.resource).count()
        self.assertEqual(before, 1, msg="fixture did not seed the blocking booking")

        with self.assertRaises(BookingConflictError):
            create_resource_booking(
                school=self.school,
                resource=self.resource,
                booked_by=self.user,
                title="Should not persist",
                start=self.base + timedelta(hours=1),
                end=self.base + timedelta(hours=3),
            )

        self.assertEqual(
            ResourceBooking.objects.filter(resource=self.resource).count(),
            before,
            msg="refused booking left a row behind",
        )
        self.assertFalse(
            ResourceBooking.objects.filter(title="Should not persist").exists()
        )

    def test_inverted_interval_is_refused_before_any_lookup(self):
        with self.assertRaises(ValueError):
            create_resource_booking(
                school=self.school,
                resource=self.resource,
                booked_by=self.user,
                title="Backwards",
                start=self.base + timedelta(hours=2),
                end=self.base,
            )
        self.assertEqual(ResourceBooking.objects.filter(resource=self.resource).count(), 0)

    def test_zero_length_interval_is_refused(self):
        with self.assertRaises(ValueError):
            create_resource_booking(
                school=self.school,
                resource=self.resource,
                booked_by=self.user,
                title="Instant",
                start=self.base,
                end=self.base,
            )

    def test_cross_school_resource_is_refused(self):
        other_school = School.objects.create(
            name="M10 Foreign",
            slug=f"m10f-{uuid.uuid4().hex[:8]}",
            subdomain=f"m10f-{uuid.uuid4().hex[:8]}",
        )
        foreign = BookableResource.objects.create(
            school=other_school, name="Foreign Hall", capacity=1
        )
        with self.assertRaises(ValueError):
            create_resource_booking(
                school=self.school,
                resource=foreign,
                booked_by=self.user,
                title="Cross tenant",
                start=self.base,
                end=self.base + timedelta(hours=1),
            )
        self.assertEqual(ResourceBooking.objects.filter(resource=foreign).count(), 0)
