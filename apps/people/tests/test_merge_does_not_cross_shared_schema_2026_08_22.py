"""A record merge must not re-point ANOTHER tenant's rows in a SHARED table.

``inbound_fk_fields`` walks the entire app registry, which is what makes the
merge walker self-maintaining -- and correct for TENANT models, because under
django-tenants each tenant's schema contains only its own rows.

A SHARED model breaks that assumption. ``compliance.FerpaDisclosure`` is in
SHARED_APPS and carries a ``db_constraint=False`` FK to
``people.StudentProfile`` (TENANT_APPS), so ONE public table holds every
tenant's disclosure rows, while StudentProfile pks are per-schema BigAutoField
sequences that collide across tenants as a matter of course. The unfiltered
``filter(student=secondary).update(student=primary)`` therefore matched another
school's disclosure rows whose ``student_id`` happened to equal this secondary's
pk, and re-parented that school's FERPA records onto a student here -- silent
cross-tenant corruption of exactly the records a disclosure log exists to
protect.

SHARED_APPS/TENANT_APPS are absent on a single-schema deploy (the local default),
so they are supplied via override_settings to exercise the cloud topology. The
pk COLLISION itself cannot be reproduced in one schema; what is pinned here is
the guard that makes it harmless -- a shared-table row belonging to a different
school is left alone.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.compliance.models import FerpaDisclosure
from apps.people.merge_service import (
    _is_shared_schema_model,
    _shared_schema_school_field,
    apply_merge,
    approve_merge,
    preview_merge,
)
from apps.people.models import StudentProfile
from apps.people.models_merge import RecordMergeOperation
from apps.schools.models import School

User = get_user_model()

_CLOUD = dict(
    SHARED_APPS=["apps.compliance", "apps.schools"],
    TENANT_APPS=["apps.people", "apps.academics"],
)


class SharedSchemaDetectionTests(TestCase):
    @override_settings(**_CLOUD)
    def test_shared_model_is_detected_and_its_school_field_found(self):
        self.assertTrue(_is_shared_schema_model(FerpaDisclosure))
        self.assertEqual(_shared_schema_school_field(FerpaDisclosure), "school")

    @override_settings(**_CLOUD)
    def test_tenant_model_is_not_treated_as_shared(self):
        self.assertFalse(_is_shared_schema_model(StudentProfile))
        self.assertIsNone(_shared_schema_school_field(StudentProfile))

    def test_single_schema_deploy_needs_no_scoping(self):
        # No SHARED_APPS => USE_DJANGO_TENANTS=0 => one table set, pks globally
        # unique, nothing to guard against.
        self.assertFalse(_is_shared_schema_model(FerpaDisclosure))


@override_settings(**_CLOUD)
class MergeLeavesOtherTenantsSharedRowsAloneTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Merge High", slug="msx-high", subdomain="msx-high"
        )
        self.other_school = School.objects.create(
            name="Other High", slug="msx-other", subdomain="msx-other"
        )
        self.operator = User.objects.create_user(
            username="msx_operator", password="pass123"
        )
        self.primary = StudentProfile.objects.create(
            school=self.school, first_name="Dupe", last_name="Licate",
            student_code="MSX-PRIMARY",
        )
        self.secondary = StudentProfile.objects.create(
            school=self.school, first_name="Dupe", last_name="Licate",
            student_code="MSX-SECOND",
        )
        # This school's disclosure -- SHOULD move to the primary.
        self.mine = FerpaDisclosure.objects.create(
            school=self.school, student=self.secondary,
            recipient_name="Ours", purpose=FerpaDisclosure.Purpose.choices[0][0],
        )
        # Another school's disclosure, in the SAME public table, pointing at the
        # same student id. Stands in for the cross-schema pk collision.
        self.theirs = FerpaDisclosure.objects.create(
            school=self.other_school, student=self.secondary,
            recipient_name="Theirs", purpose=FerpaDisclosure.Purpose.choices[0][0],
        )
        self.op = RecordMergeOperation.objects.create(
            school=self.school,
            kind=RecordMergeOperation.Kind.STUDENT,
            primary_pk=str(self.primary.pk),
            secondary_pk=str(self.secondary.pk),
            created_by=self.operator,
        )

    def test_other_schools_disclosure_is_not_repointed(self):
        preview_merge(self.op)
        approve_merge(self.op, self.operator)
        apply_merge(self.op, actor=self.operator)

        self.mine.refresh_from_db()
        self.theirs.refresh_from_db()
        self.assertEqual(
            self.mine.student_id, self.primary.pk,
            "this school's disclosure should have moved to the primary",
        )
        self.assertEqual(
            self.theirs.student_id, self.secondary.pk,
            "another school's row in the SHARED table must be untouched",
        )
        self.assertEqual(self.theirs.school_id, self.other_school.pk)
