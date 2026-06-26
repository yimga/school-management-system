"""Resource booking: service layer + Postgres exclusion constraint."""

from __future__ import annotations

import unittest
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, skipUnlessDBFeature, tag
from django.utils import timezone

from apps.schoolops.booking_services import (
    BookingConflictError,
    cancel_resource_booking,
    create_resource_booking,
)
from apps.schoolops.models import BookableResource, ResourceBooking
from apps.schools.models import School

User = get_user_model()

requires_postgres = unittest.skipUnless(
    connection.vendor == "postgresql",
    "Resource booking requires PostgreSQL (DateTimeRangeField + gist exclusion)",
)


class ResourceBookingModuleSmokeTests(TestCase):
    def test_models_and_service_import(self):
        from apps.schoolops import booking_services as mod
        from apps.schoolops.models_resource_booking import ResourceBooking as RB

        self.assertTrue(RB._meta.constraints)
        self.assertTrue(callable(mod.create_resource_booking))


@requires_postgres
@tag("tenants_rls")
class ResourceBookingServiceTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Booking School",
            slug=f"bk-{uuid.uuid4().hex[:10]}",
            subdomain=f"bk-{uuid.uuid4().hex[:10]}",
        )
        self.user = User.objects.create_user(
            username=f"u-{uuid.uuid4().hex[:8]}",
            email="b@test.local",
            password="x",
            role=User.Role.ADMIN,
        )
        self.resource = BookableResource.objects.create(
            school=self.school,
            name="Science Lab",
            capacity=1,
        )

    def test_non_overlapping_bookings_allowed(self):
        base = timezone.now().replace(minute=0, second=0, microsecond=0)
        create_resource_booking(
            school=self.school,
            resource=self.resource,
            booked_by=self.user,
            title="Morning",
            start=base,
            end=base + timedelta(hours=1),
        )
        create_resource_booking(
            school=self.school,
            resource=self.resource,
            booked_by=self.user,
            title="Afternoon",
            start=base + timedelta(hours=2),
            end=base + timedelta(hours=3),
        )
        self.assertEqual(
            ResourceBooking.objects.filter(school=self.school).count(),
            2,
        )

    def test_service_rejects_overlap_before_db(self):
        base = timezone.now().replace(minute=0, second=0, microsecond=0)
        create_resource_booking(
            school=self.school,
            resource=self.resource,
            booked_by=self.user,
            title="First",
            start=base,
            end=base + timedelta(hours=2),
        )
        with self.assertRaises(BookingConflictError):
            create_resource_booking(
                school=self.school,
                resource=self.resource,
                booked_by=self.user,
                title="Overlap",
                start=base + timedelta(hours=1),
                end=base + timedelta(hours=3),
            )

    def test_fractional_capacity_allows_two_when_capacity_two(self):
        hall = BookableResource.objects.create(
            school=self.school,
            name="Main Hall",
            capacity=2,
        )
        base = timezone.now().replace(minute=0, second=0, microsecond=0)
        create_resource_booking(
            school=self.school,
            resource=hall,
            booked_by=self.user,
            title="Event A",
            start=base,
            end=base + timedelta(hours=1),
        )
        create_resource_booking(
            school=self.school,
            resource=hall,
            booked_by=self.user,
            title="Event B",
            start=base,
            end=base + timedelta(hours=1),
        )
        with self.assertRaises(BookingConflictError):
            create_resource_booking(
                school=self.school,
                resource=hall,
                booked_by=self.user,
                title="Event C",
                start=base,
                end=base + timedelta(hours=1),
            )

    def test_cancel_frees_slot(self):
        base = timezone.now().replace(minute=0, second=0, microsecond=0)
        booking = create_resource_booking(
            school=self.school,
            resource=self.resource,
            booked_by=self.user,
            title="Temp",
            start=base,
            end=base + timedelta(hours=1),
        )
        cancel_resource_booking(booking=booking)
        create_resource_booking(
            school=self.school,
            resource=self.resource,
            booked_by=self.user,
            title="After cancel",
            start=base,
            end=base + timedelta(hours=1),
        )


@requires_postgres
@tag("tenants_rls")
@skipUnlessDBFeature("supports_table_check_constraints")
class ResourceBookingPostgresExclusionTests(TestCase):
    """Requires Postgres + btree_gist for ExclusionConstraint enforcement."""

    def setUp(self):
        self.school = School.objects.create(
            name="PG Booking",
            slug=f"pg-{uuid.uuid4().hex[:10]}",
            subdomain=f"pg-{uuid.uuid4().hex[:10]}",
        )
        self.user = User.objects.create_user(
            username=f"pg-{uuid.uuid4().hex[:8]}",
            email="pg@test.local",
            password="x",
            role=User.Role.ADMIN,
        )
        self.resource = BookableResource.objects.create(
            school=self.school,
            name="Lab 1",
            capacity=1,
        )

    def test_db_exclusion_blocks_race_overlap(self):
        """Second overlapping insert must fail (IntegrityError → BookingConflictError)."""
        base = timezone.now().replace(minute=0, second=0, microsecond=0)
        create_resource_booking(
            school=self.school,
            resource=self.resource,
            booked_by=self.user,
            title="Held",
            start=base,
            end=base + timedelta(hours=2),
        )
        with self.assertRaises(BookingConflictError):
            create_resource_booking(
                school=self.school,
                resource=self.resource,
                booked_by=self.user,
                title="Race overlap",
                start=base + timedelta(minutes=30),
                end=base + timedelta(hours=3),
            )
