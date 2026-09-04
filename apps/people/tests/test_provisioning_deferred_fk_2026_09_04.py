"""The queue write's promise, tested on the substrate that can break it.

``record_refused_insert`` says "Never raises into the rail", and on SQLite that
is true: a bad row raises inside the try and the bare except swallows it. On
PostgreSQL it is not a claim about the call at all. Django declares foreign keys
DEFERRABLE INITIALLY DEFERRED, so an insert naming a school that does not exist
SUCCEEDS, the inner savepoint releases cleanly, and the function returns a row
and reports success. The violation is raised at COMMIT -- by which point it is
no longer a queue write failing, it is the entire sync cycle failing, which is
the one outcome this function exists to prevent.

That is why these assertions call ``check_constraints()`` explicitly. Inside a
TestCase nothing ever commits, so a deferred violation would otherwise sit
undetected and the test would pass while the product was broken.
"""

import uuid

from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.people.models_provisioning import ProvisioningRequest
from apps.people.provisioning_service import record_refused_insert
from apps.schools.models import School

MISSING_SCHOOL_PK = uuid.UUID("d7f4c1a2-3b56-4e89-9c01-2f6a8b4d5e30")


class TheQueueWriteNeverReachesCommitBrokenTests(TestCase):
    def test_the_premise(self):
        """Guard the guard: the pk really is absent, or the test proves nothing."""
        self.assertFalse(School.objects.filter(pk=MISSING_SCHOOL_PK).exists())

    def test_a_school_that_does_not_exist_is_declined_not_deferred(self):
        row = record_refused_insert(
            school_id=MISSING_SCHOOL_PK,
            entity_type="teacher",
            client_offline_id="box-ghost-1",
            values={"first_name": "Ada", "last_name": "Nkeng"},
        )
        self.assertIsNone(
            row,
            "a queue write for a school that does not exist must be declined at "
            "the call, not handed to COMMIT as a deferred constraint violation",
        )
        self.assertEqual(ProvisioningRequest.objects.count(), 0)

    def test_the_surrounding_transaction_is_still_usable_afterwards(self):
        """The refusal is still correct and the cycle still finishes.

        This is the assertion that fails loudly on Postgres if the row was
        allowed through: check_constraints() is where a deferred violation
        surfaces, and a sync cycle reaches that point with real work behind it.
        """
        record_refused_insert(
            school_id=MISSING_SCHOOL_PK,
            entity_type="teacher",
            client_offline_id="box-ghost-2",
            values={"first_name": "Ada"},
        )
        try:
            connection.check_constraints()
        except IntegrityError as exc:  # pragma: no cover - the failure path
            self.fail(
                "the queue write left a deferred constraint violation that will "
                "abort the sync cycle at COMMIT: %s" % exc
            )
        self.assertEqual(ProvisioningRequest.objects.count(), 0)

    def test_a_real_school_still_records_normally(self):
        """The fix must not close the door on the case that matters."""
        school = School.objects.create(
            name="Ghost Guard School",
            slug="ghost-guard-school",
            subdomain="ghost-guard-school",
            is_active=True,
            country_code="CM",
        )
        with transaction.atomic():
            row = record_refused_insert(
                school_id=school.pk,
                entity_type="teacher",
                client_offline_id="box-real-1",
                values={"first_name": "Ada", "last_name": "Nkeng"},
            )
        self.assertIsNotNone(row)
        self.assertEqual(row.school_id, school.pk)
        connection.check_constraints()
