"""Which SCHEMA the staff bundle reads and writes -- the one thing the box cannot test.

WHY THIS FILE EXISTS. `export_tenant_staff` was pk-preserving, `import_tenant_staff` was
pk-preserving, both were signature-verified, and together they still could not converge a
single teacher. Measured on the live deployment, 2026-08-30:

    public                              39 rows, ids 28-66   <- what the export read
    s_f984ea95d2ad4900b51366a345928316  39 rows, ids  2-40   <- what the sync rail serves

A management command runs in `public`; the bundle-download endpoint is an HTTP view, so
tenant middleware had already switched schema. The export faithfully copied the pks of the
wrong table. The box then refused all 26 pulled teacher rows as `insert_held_for_entity`
-- not because the identity hold was wrong, but because a lookup by a pk minted in another
schema can only ever miss, forever, through any number of resyncs.

WHY IT WAS INVISIBLE, and why these tests look the way they do. On a sovereign box
`USE_DJANGO_TENANTS=0`: one schema, and every existing staff test passes whether or not a
schema switch is present, because in one schema "the wrong table" does not exist. The
suite runs single-schema too. A test can only see this defect by asserting WHERE the read
happened, so that is what these assert.

THEY PATCH ONLY WHAT ALSO EXISTS ON THE BROKEN TREE. An earlier draft mocked a helper the
fix introduces, so on the unfixed tree it died with AttributeError inside mock.patch --
red, and meaningless: it proved the helper was new, not that the read moved. `tenant_context`,
`_teacher_rows` and `_teacher_model` all predate the fix, and the tenant client is a real
row, so the only difference between a pass and a fail here is the behaviour under test.
"""
from __future__ import annotations

import contextlib
import uuid
from unittest import mock

import django_tenants.utils as dtu
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.customers.models import Client
from apps.lifecycle import staff_portability as sp
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership


class _SchemaSpy:
    """Records every tenant_context entry, and how deep we are at any moment."""

    def __init__(self):
        self.depth = 0
        self.entered = []

    def tenant_context(self, client):
        @contextlib.contextmanager
        def _cm():
            self.depth += 1
            self.entered.append(getattr(client, "schema_name", None))
            try:
                yield
            finally:
                self.depth -= 1

        return _cm()


def _school_with_teachers(prefix, n=2):
    uid = uuid.uuid4().hex[:8]
    school = School.objects.create(
        name=f"{prefix} {uid}",
        slug=f"{prefix}-{uid}",
        subdomain=f"{prefix}{uid}",
        is_active=True,
    )
    owner = User.objects.create_user(
        username=f"own_{uid}", password="Test1234", email=f"o{uid}@t.com"
    )
    SchoolMembership.objects.create(
        user=owner, school=school, role="ADMIN", is_primary=True
    )
    for i in range(n):
        u = User.objects.create_user(
            username=f"tt{i}_{uid}", password="Test1234", email=f"t{i}{uid}@t.com"
        )
        TeacherProfile.objects.create(school=school, user=u, staff_id=f"SS-{i}-{uid}")
    return school, uid


def _give_tenant_client(school, uid):
    """A REAL customers.Client, without provisioning a PostgreSQL schema.

    django-tenants' TenantMixin.save() only calls create_schema when the instance's
    auto_create_schema is true, so clearing it on the instance keeps this a plain row --
    which is what the test needs, and what makes the reverse OneToOne resolve identically
    on the fixed and unfixed trees.
    """
    client = Client(name=school.name, school=school, schema_name=f"s_{uid}")
    client.auto_create_schema = False
    client.save()
    return client


@override_settings(USE_DJANGO_TENANTS=True)
class ExportReadsTheTenantSchemaTests(TestCase):
    def test_the_teacher_rows_are_read_INSIDE_the_tenant_schema(self):
        """THE DEFECT, pinned. On the unfixed tree this depth is 0, not 1."""
        school, uid = _school_with_teachers("inside")
        _give_tenant_client(school, uid)

        spy = _SchemaSpy()
        seen = {}
        real_rows = sp._teacher_rows

        def _watched(target):
            seen["depth"] = spy.depth
            return real_rows(target)

        with mock.patch.object(dtu, "tenant_context", spy.tenant_context), \
                mock.patch.object(sp, "_teacher_rows", _watched):
            sp.export_staff_bundle(school)

        self.assertEqual(
            seen.get("depth"),
            1,
            "the teacher table was read on the DEFAULT connection -- i.e. in public on a "
            "schema-per-tenant deployment, which is the exact bug this file exists for",
        )
        self.assertEqual(spy.entered, [f"s_{uid}"])

    def test_the_import_writes_INSIDE_the_tenant_schema(self):
        """The same property on the way back in."""
        school, uid = _school_with_teachers("impin")
        _give_tenant_client(school, uid)

        with mock.patch.object(dtu, "tenant_context", _SchemaSpy().tenant_context):
            data = sp.export_staff_bundle(school)

        spy = _SchemaSpy()
        seen = {}
        real_model = sp._teacher_model

        def _watched():
            seen.setdefault("depth", spy.depth)
            return real_model()

        with mock.patch.object(dtu, "tenant_context", spy.tenant_context), \
                mock.patch.object(sp, "_teacher_model", _watched):
            sp.import_staff_bundle(data, expected_school_id=school.id)

        self.assertEqual(
            seen.get("depth"), 1, "staff were landed on the DEFAULT connection"
        )

    def test_it_REFUSES_rather_than_falling_back_to_public(self):
        """Fail closed. A silent fall-back is how the wrong 39 rows got signed and shipped."""
        school, _uid = _school_with_teachers("noclient")  # deliberately NO tenant client
        with self.assertRaises(ValueError) as ctx:
            sp.export_staff_bundle(school)
        self.assertIn("staff_bundle_no_tenant_schema", str(ctx.exception))


class SingleSchemaBoxIsUntouchedTests(TestCase):
    """The CONTROL half. Without these, making the switch UNCONDITIONAL would satisfy the
    tests above while breaking every sovereign box, where there is no tenant client at all
    and a refusal would make staff import impossible."""

    def test_no_schema_switch_is_attempted_under_RLS(self):
        school, _uid = _school_with_teachers("rls")
        spy = _SchemaSpy()
        with mock.patch.object(dtu, "tenant_context", spy.tenant_context):
            sp.export_staff_bundle(school)
        self.assertEqual(
            spy.entered,
            [],
            "USE_DJANGO_TENANTS=0 is one shared schema; switching would be wrong, not "
            "merely redundant",
        )

    def test_the_round_trip_still_works_with_no_tenant_client(self):
        """The box has no customers.Client, and must still be able to take staff."""
        school, _uid = _school_with_teachers("rt2", n=3)
        pks = sorted(
            TeacherProfile.objects.filter(school=school).values_list("pk", flat=True)
        )

        data = sp.export_staff_bundle(school)
        TeacherProfile.objects.filter(school=school).delete()
        self.assertEqual(TeacherProfile.objects.filter(school=school).count(), 0)

        result = sp.import_staff_bundle(data, expected_school_id=school.id)
        self.assertEqual(result["teachers"], 3)
        self.assertEqual(
            sorted(
                TeacherProfile.objects.filter(school=school).values_list("pk", flat=True)
            ),
            pks,
            "pk preservation is the property the whole module rests on",
        )
