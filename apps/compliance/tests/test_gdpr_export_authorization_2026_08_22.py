"""``/compliance/gdpr/export/`` must be bound to the data subject, not just the module.

An automated audit reported this view as reachable by "any authenticated tenant
user", because it carries only ``@login_required`` with no role or permission
check. That overstates it: ``/compliance/`` is behind
``can_access_module(user, "compliance", "read")``, whose role set is
{ADMIN, SUPERADMIN, IT_ADMIN, LEADERSHIP, PRINCIPAL, VICE_PRINCIPAL, DEAN} -- a
STUDENT, PARENT or TEACHER gets a 403 from the module gate and never reaches the
view. Verified by request.

What IS real is the gap between that set and ``STUDENT_DATA_GLOBAL_ROLES``
{SUPERADMIN, ADMIN, LEADERSHIP, PRINCIPAL, VICE_PRINCIPAL, DEAN, CENSOR, HOD,
DEPT_LEAD}. Exactly one role sits in the first and not the second: **IT_ADMIN**.
So a technical administrator could export any student's full GDPR Art. 20
portability payload -- identifiers, contacts, guardians, health and discipline
records -- which is a data-protection action, not a technical one.

The view now consults ``can_view_student_data``, which also keeps the surface
correct if the module set is ever widened: Art. 20 is a right OF THE SUBJECT, so
a PARENT or STUDENT admitted to this module in future still gets their own record
and nobody else's.
"""

from __future__ import annotations

import uuid

from django.test import RequestFactory, TestCase

from apps.academics.models import AcademicYear
from apps.accounts.models import User
from apps.accounts.permissions import (
    MODULE_ACCESS_DEFAULTS,
    STUDENT_DATA_GLOBAL_ROLES,
    can_view_student_data,
)
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership


class GdprExportAuthorizationTests(TestCase):
    def setUp(self) -> None:
        self.school = School.objects.create(
            name="GDPR High",
            slug=f"gd-{uuid.uuid4().hex[:8]}",
            subdomain=f"gd-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-08-31",
            is_active=True,
        )
        self.victim = StudentProfile.objects.create(
            school=self.school,
            first_name="Victim",
            last_name="Student",
            student_code=f"GD-V-{uuid.uuid4().hex[:6]}",
            academic_year=self.year,
            is_active=True,
        )

    def _user(self, role):
        u = User.objects.create_user(
            username=f"gd-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:6]}@example.com",
            password="testpass123",
            role=role,
        )
        SchoolMembership.objects.create(user=u, school=self.school, role=role)
        return u

    def _get(self, user):
        """Call the view directly with a bound school.

        RequestFactory, matching test_control_plane_boundaries.py: under the test
        client no host resolves to this tenant, so request.school is None and the
        view returns its own "School context required." 403 before reaching any
        authorization -- which would make the assertion vacuous.
        """
        from apps.compliance.views_gdpr import data_portability_export

        request = RequestFactory().get(
            "/compliance/gdpr/export/", {"student_id": str(self.victim.pk)}
        )
        request.user = user
        request.school = self.school
        request.session = {}
        return data_portability_export(request)

    def test_it_admin_is_denied_the_student(self) -> None:
        """The one role in the module set and NOT in the student-data set."""
        response = self._get(self._user("IT_ADMIN"))
        self.assertEqual(response.status_code, 403, response.content[:200])
        import json as _json

        self.assertEqual(
            _json.loads(response.content).get("error"),
            "Not authorized for this student",
            "must be the VIEW's own refusal",
        )

    def test_principal_still_gets_a_payload(self) -> None:
        # The fix must not break the legitimate path: a PRINCIPAL is in
        # STUDENT_DATA_GLOBAL_ROLES and must still pass the view's check.
        response = self._get(self._user("PRINCIPAL"))
        self.assertNotEqual(
            response.status_code, 403, "leadership must keep its export"
        )

    def test_leadership_still_gets_the_export(self) -> None:
        # The fix must not break the legitimate path.
        principal = self._user("PRINCIPAL")
        self.assertTrue(can_view_student_data(principal, self.victim.pk))

    def test_the_role_gap_this_closes_is_exactly_it_admin(self) -> None:
        """Pins WHY this fix exists, so a future role edit re-opens it loudly."""
        module_read = set(MODULE_ACCESS_DEFAULTS["compliance"]["read"])
        gap = module_read - set(STUDENT_DATA_GLOBAL_ROLES)
        self.assertEqual(
            gap,
            {"IT_ADMIN"},
            "roles that can open the compliance module but may not read student "
            "data -- if this set grows, the export surface widened",
        )
