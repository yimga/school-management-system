"""Portability must read and write the school's OWN schema, never `public`.

Measured on the deployed cloud, 2026-08-31, for one live school:

    public                              56 teachers  (39 tagged for this school,
                                                      16 orphaned, 1 ANOTHER SCHOOL'S)
                                       204 students  (none of them this school's)
    s_f984ea95d2ad4900b51366a345928316  40 teachers, 538 students   <- the live roster

Neither portability module entered a schema. `tenant_portability._scope_queryset`
DROPS the school filter under `USE_DJANGO_TENANTS=1` -- correct inside the tenant
schema, an unfiltered read of `public` outside it -- so the sovereign bundle shipped
another tenant's row. `staff_portability` kept its school filter and so merely moved a
legacy copy of the roster: same people, different pks, not what the tenant UI serves,
and therefore pks the sync rail could never match.

WHAT THESE TESTS CAN AND CANNOT PROVE
-------------------------------------
PostgreSQL schemas do not exist on SQLite and the local suite runs with
`USE_DJANGO_TENANTS=0`, so nothing here executes a real `SET search_path`. Stated
plainly rather than implied: **the schema-switching behaviour itself is not covered
here.** What IS pinned is the contract that was missing -- that a schema is entered at
all, that it is the school's own, that provenance is recorded, and that an unresolvable
schema fails CLOSED instead of quietly reading `public`. That last one is the whole
defect: the old code did not fail, it succeeded against the wrong table.
"""
from __future__ import annotations

import base64
import gzip
import json
import uuid
from contextlib import contextmanager
from unittest import mock

from django.test import TestCase

from apps.accounts.models import User
from apps.lifecycle.schema_scope import resolve_schema, schema_per_tenant, school_schema
from apps.lifecycle.staff_portability import export_staff_bundle, import_staff_bundle
from apps.lifecycle.tenant_dr_snapshot import decrypt_blob
from apps.lifecycle.tenant_portability import export_tenant_bundle
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership

_RESOLVER = "apps.migration_cloud.schema_binding.resolve_school_schema_name"


def _school(prefix="scope"):
    uid = uuid.uuid4().hex[:8]
    school = School.objects.create(
        name=f"{prefix} {uid}",
        slug=f"{prefix}-{uid}",
        subdomain=f"{prefix}{uid}",
        is_active=True,
    )
    owner = User.objects.create_user(
        username=f"owner_{uid}", password="Test1234", email=f"o{uid}@t.com"
    )
    SchoolMembership.objects.create(user=owner, school=school, role="ADMIN", is_primary=True)
    return school, uid


def _teacher(school, uid):
    user = User.objects.create_user(
        username=f"t_{uid}", password="Test1234", email=f"t{uid}@t.com"
    )
    TeacherProfile.objects.create(school=school, user=user, staff_id=f"S-{uid}")
    return user


def _decrypt(data: bytes, school) -> dict:
    container = json.loads(data)
    return json.loads(
        gzip.decompress(
            decrypt_blob(base64.b64decode(container["blob_b64"]), school_id=str(school.id))
        )
    )


@contextmanager
def _recording_scope(sink, name="s_test"):
    """Stand-in for `school_schema` that records what it was asked to enter."""

    @contextmanager
    def _scope(school):
        sink.append(school)
        yield name

    yield _scope


class SchemaScopeContractTests(TestCase):
    def test_a_single_schema_deployment_is_left_alone(self):
        """A sovereign box has one schema. The old behaviour is correct there."""
        with self.settings(USE_DJANGO_TENANTS=False):
            self.assertFalse(schema_per_tenant())
            self.assertEqual(resolve_schema(object()), "")
            with school_schema(object()) as entered:
                self.assertEqual(entered, "")

    def test_an_unresolvable_schema_is_refused_not_silently_public(self):
        """The defect was never a crash -- it was success against the wrong table."""
        school, _uid = _school("unres")
        with self.settings(USE_DJANGO_TENANTS=True):
            with mock.patch(_RESOLVER, return_value=""):
                with self.assertRaises(ValueError) as ctx:
                    with school_schema(school):
                        pass
        self.assertIn("tenant_schema_unresolved", str(ctx.exception))

    def test_it_enters_the_schools_own_schema(self):
        school, _uid = _school("own")
        entered = []

        @contextmanager
        def fake_schema_context(name):
            entered.append(name)
            yield

        with self.settings(USE_DJANGO_TENANTS=True):
            with mock.patch(_RESOLVER, return_value="s_deadbeef"):
                with mock.patch("django_tenants.utils.schema_context", fake_schema_context):
                    with school_schema(school) as name:
                        self.assertEqual(name, "s_deadbeef")
        self.assertEqual(entered, ["s_deadbeef"], "the resolved schema must be entered")


class StaffExportIsScopedTests(TestCase):
    def test_the_profile_read_happens_inside_the_scope(self):
        school, uid = _school("sx")
        _teacher(school, uid)
        seen = []

        with _recording_scope(seen) as scope:
            with mock.patch("apps.lifecycle.staff_portability.school_schema", scope):
                data = export_staff_bundle(school)

        self.assertEqual(seen, [school], "the export must scope to THIS school")
        self.assertEqual(_decrypt(data, school)["source_schema"], "s_test")

    def test_it_refuses_to_export_when_the_schema_cannot_be_resolved(self):
        """The behavioural proof, needing no patch of our own symbols.

        Against the previous code this returned a perfectly valid signed bundle built
        from `public`. Silent success against the wrong table is the defect; refusing
        is the fix.
        """
        school, uid = _school("failclosed")
        _teacher(school, uid)
        with self.settings(USE_DJANGO_TENANTS=True):
            with mock.patch(_RESOLVER, return_value=""):
                with self.assertRaises(ValueError) as ctx:
                    export_staff_bundle(school)
        self.assertIn("tenant_schema_unresolved", str(ctx.exception))

    def test_the_bundle_records_which_schema_it_came_from(self):
        """Provenance is the one field that separates a good bundle from a `public` one."""
        school, uid = _school("prov")
        _teacher(school, uid)
        payload = _decrypt(export_staff_bundle(school), school)
        self.assertIn("source_schema", payload)

    def test_the_import_writes_inside_the_scope(self):
        school, uid = _school("imp")
        user = _teacher(school, uid)
        data = export_staff_bundle(school)
        User.objects.filter(pk=user.pk).delete()
        seen = []

        with _recording_scope(seen) as scope:
            with mock.patch("apps.lifecycle.staff_portability.school_schema", scope):
                result = import_staff_bundle(data, expected_school_id=school.id)

        self.assertEqual(result["teachers"], 1)
        self.assertEqual(
            [getattr(s, "pk", None) for s in seen],
            [school.pk],
            "the write must land in the target school's schema, not the connection's",
        )


class TenantBundleIsScopedTests(TestCase):
    def test_the_export_reads_inside_the_scope(self):
        """The worse of the two: in schema mode this read has NO school filter."""
        school, uid = _school("tb")
        _teacher(school, uid)
        seen = []

        with _recording_scope(seen) as scope:
            with mock.patch("apps.lifecycle.tenant_portability.school_schema", scope):
                data = export_tenant_bundle(school)

        self.assertEqual(seen, [school])
        self.assertEqual(_decrypt(data, school)["source_schema"], "s_test")

    def test_it_refuses_to_export_when_the_schema_cannot_be_resolved(self):
        """Same behavioural proof for the bundle that carried another tenant's row."""
        school, uid = _school("tbfail")
        _teacher(school, uid)
        with self.settings(USE_DJANGO_TENANTS=True):
            with mock.patch(_RESOLVER, return_value=""):
                with self.assertRaises(ValueError) as ctx:
                    export_tenant_bundle(school)
        self.assertIn("tenant_schema_unresolved", str(ctx.exception))
