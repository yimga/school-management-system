"""The backend dashboard's Pending Approvals tile must count only this school's.

``apps.requests`` is a SHARED app (``config/settings.py``), so
``requests_accessrequest`` lives in the public schema and every tenant's
``search_path`` can see all of it.  The surrounding tenant context is a Postgres
schema, and a schema does not scope a shared table -- so an unfiltered
``.count()`` there reports the platform's whole pending queue to one school's
admin.  ``AccessRequest`` carries a ``school`` FK, and the requests LIST view
already filters on it, so the tile and the page it links to disagreed.

``apps/dashboard/admin_context.py`` already learned this for ``/admin/``
("Shared identity tables must never expose platform-wide aggregates to a tenant
`/admin/`"); ``context.py`` never did.
"""

from __future__ import annotations

import uuid

from django.core.cache import cache
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.requests.models import AccessRequest
from apps.schools.models import School, SchoolMembership


class BackendSnapshotPendingApprovalsScopeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name="Mine {0}".format(uid),
            slug="mine-{0}".format(uid),
            subdomain="mine{0}".format(uid),
            is_active=True,
        )
        self.other = School.objects.create(
            name="Theirs {0}".format(uid),
            slug="theirs-{0}".format(uid),
            subdomain="theirs{0}".format(uid),
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="admin{0}".format(uid),
            password="Test1234",
            email="a{0}@test.com".format(uid),
            role="ADMIN",
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.rf = RequestFactory()

    def _pending(self, school, n):
        for _ in range(n):
            AccessRequest.objects.create(
                school=school,
                request_type="ACCESS",
                status=AccessRequest.Status.PENDING,
                title="Needs a decision",
            )

    def _watch_value(self, key):
        from apps.dashboard.context import build_dashboard_extras

        request = self.rf.get("/backend/", HTTP_HOST="{0}.runmycampus.com".format(self.school.subdomain))
        request.user = self.user
        request.school = self.school
        extras = build_dashboard_extras(request)
        watch = {item["key"]: item["value"] for item in extras["operations_watch"]}
        return watch[key]

    def test_other_schools_pending_requests_are_not_counted(self):
        self._pending(self.other, 11)
        self.assertEqual(self._watch_value("pending_approvals"), 0)

    def test_this_schools_pending_requests_are_counted(self):
        """Not vacuous: the query really does reach the table for the bound school.

        Without this, a snapshot that simply failed (import error, DatabaseError
        swallowed by ``_DASHBOARD_SNAPSHOT_ERRORS``) would satisfy the test above
        while measuring nothing at all.
        """
        self._pending(self.school, 3)
        self._pending(self.other, 11)
        self.assertEqual(self._watch_value("pending_approvals"), 3)
