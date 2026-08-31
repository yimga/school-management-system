"""The SOVEREIGN bundle must be read from the tenant schema too, not from `public`.

The staff half of this bug is covered by ``test_staff_export_tenant_schema_2026_08_30``.
This file is the other half, which that work did not reach and which is the more
dangerous of the two.

``_scope_queryset`` branches on the tenancy flag and returns
``model._default_manager.all()``, reasoning in its own comment that "the schema IS the
tenant -- every row belongs to it". That is true INSIDE the tenant schema. Outside it --
which is where a management command runs, because django-tenants binds a schema from the
REQUEST -- it is an unfiltered read of ``public`` with the school filter deliberately
dropped.

Measured on the deployed cloud, 2026-08-31, for one live school::

    public                              56 teachers  (39 tagged for this school,
                                                      16 orphaned, 1 ANOTHER SCHOOL'S)
                                       204 students  (none of them this school's)
    s_f984ea95d2ad4900b51366a345928316  40 teachers, 538 students   <- the live roster

So ``export_tenant_bundle`` shipped one tenant's row inside another tenant's bundle, and
none of the school's real 538 students.

WHAT THIS CAN AND CANNOT PROVE
------------------------------
PostgreSQL schemas do not exist on SQLite and the local suite runs with
``USE_DJANGO_TENANTS=0``, so nothing here executes a real ``SET search_path``: **the
switching itself is not covered.** What is pinned is that the scope is entered at all,
that it is entered for THIS school, and that an unresolvable schema fails CLOSED. That
last one is the defect in one sentence -- the old code did not crash, it succeeded
against the wrong table.
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
from apps.lifecycle.tenant_dr_snapshot import decrypt_blob
from apps.lifecycle.tenant_portability import export_tenant_bundle, import_tenant_bundle
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership


def _school(prefix="tbs"):
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
    user = User.objects.create_user(
        username=f"t_{uid}", password="Test1234", email=f"t{uid}@t.com"
    )
    TeacherProfile.objects.create(school=school, user=user, staff_id=f"S-{uid}")
    return school, uid


def _decrypt(data: bytes, school) -> dict:
    container = json.loads(data)
    return json.loads(
        gzip.decompress(
            decrypt_blob(base64.b64decode(container["blob_b64"]), school_id=str(school.id))
        )
    )


@contextmanager
def _recorder(sink):
    """Stand-in for `school_schema` that records what it was asked to enter."""

    @contextmanager
    def _scope(school):
        sink.append(school)
        yield

    yield _scope


class TenantBundleIsSchemaScopedTests(TestCase):
    def test_the_export_reads_inside_the_scope(self):
        school, _uid = _school("read")
        seen = []
        with _recorder(seen) as scope:
            with mock.patch("apps.lifecycle.tenant_portability.school_schema", scope):
                data = export_tenant_bundle(school)
        self.assertEqual(seen, [school], "the export must scope to THIS school")
        self.assertIn("people.teacherprofile", _decrypt(data, school)["tables"])

    def test_the_import_writes_inside_the_scope(self):
        school, _uid = _school("write")
        data = export_tenant_bundle(school)
        seen = []
        with _recorder(seen) as scope:
            with mock.patch("apps.lifecycle.tenant_portability.school_schema", scope):
                import_tenant_bundle(data, expected_school_id=school.id)
        self.assertEqual(
            [getattr(s, "pk", None) for s in seen],
            [school.pk],
            "rows must land in the target school's schema, not the connection's",
        )

    def test_it_refuses_to_export_when_the_school_has_no_tenant_schema(self):
        """The behavioural proof: no patching of our own symbols.

        Against the previous code this returned a perfectly valid signed bundle built
        from `public`. Silent success against the wrong table IS the defect.
        """
        school, _uid = _school("closed")
        with self.settings(USE_DJANGO_TENANTS=True):
            with self.assertRaises(ValueError) as ctx:
                export_tenant_bundle(school)
        self.assertIn("no_tenant_schema", str(ctx.exception))

    def test_a_sovereign_box_is_unaffected(self):
        """One schema, nothing to enter — the previous behaviour is correct there."""
        school, _uid = _school("box")
        with self.settings(USE_DJANGO_TENANTS=False):
            payload = _decrypt(export_tenant_bundle(school), school)
        self.assertEqual(payload["mode"], "rls")
        self.assertIn("people.teacherprofile", payload["tables"])

    def test_the_bundle_records_which_schema_it_came_from(self):
        """Provenance separates a good bundle from one built against `public`."""
        school, _uid = _school("prov")
        self.assertIn("source_schema", _decrypt(export_tenant_bundle(school), school))
