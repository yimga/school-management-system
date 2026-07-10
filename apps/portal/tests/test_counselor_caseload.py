"""MTSS counselor caseload dashboard (metric 11).

Covers: renders for a user holding ``discipline.manage`` (200) with the right
students on the caseload; the tenant-admin tier passes; a user without the code is
forbidden (PermissionDenied -> handler403 -> 403); anonymous is redirected to login;
and the caseload is strictly school-scoped (a student in another school never leaks).
"""

import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase, override_settings

from apps.academics.models import Incident
from apps.accounts.models import Permission
from apps.people.models import StudentProfile
from apps.portal.views_teacher import counselor_caseload
from apps.schools.models import School

User = get_user_model()


def _school(tag):
    return School.objects.create(
        name=f"Caseload {tag}",
        slug=f"cl-{tag}-{uuid.uuid4().hex[:8]}",
        subdomain=f"cl-{tag}-{uuid.uuid4().hex[:8]}",
    )


def _student(school, first, last):
    return StudentProfile.objects.create(
        school=school,
        first_name=first,
        last_name=last,
        student_code=f"ST-{uuid.uuid4().hex[:6]}",
    )


@override_settings(ROOT_URLCONF="config.tenant_urls")
class CounselorCaseloadTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = _school("A")
        self.other_school = _school("B")

        # In-caseload student: recent, Tier 2, HIGH severity, OPEN -> auto ledger + restorative.
        # Distinctive surnames so substring asserts never collide with the portal shell.
        self.pat = _student(self.school, "Patricia", "Vandersloot")
        Incident.objects.create(
            school=self.school,
            student=self.pat,
            incident_type=Incident.Type.BEHAVIOR,
            severity=Incident.Severity.HIGH,
            mtss_tier=Incident.MtssTier.TIER_2,
            date=date.today(),
            notify_parent=True,  # left un-notified in setUp -> pending backlog
        )

        # Excluded student: Tier 1, resolved, and far in the past (no criterion met).
        self.old = _student(self.school, "Olden", "Thistlewood")
        Incident.objects.create(
            school=self.school,
            student=self.old,
            incident_type=Incident.Type.TARDINESS,
            severity=Incident.Severity.LOW,
            mtss_tier=Incident.MtssTier.TIER_1,
            status=Incident.Status.RESOLVED,
            date=date.today() - timedelta(days=400),
            notify_parent=False,
        )

        # Other-school student: Tier 3, recent -> in THAT school's caseload only.
        self.zed = _student(self.other_school, "Zedediah", "Quillfeather")
        Incident.objects.create(
            school=self.other_school,
            student=self.zed,
            incident_type=Incident.Type.BEHAVIOR,
            severity=Incident.Severity.HIGH,
            mtss_tier=Incident.MtssTier.TIER_3,
            date=date.today(),
            notify_parent=False,
        )

        # Counselor: no admin-like role; only the granted feature permission opens the gate.
        self.counselor = User.objects.create_user(
            username=f"couns-{uuid.uuid4().hex[:8]}",
            email="c@caseload.test",
            password="x",
            role=User.Role.TEACHER,
        )
        perm, _ = Permission.objects.get_or_create(
            code="discipline.manage",
            defaults={"name": "Discipline management"},
        )
        self.counselor.feature_permissions.add(perm)

        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:8]}",
            email="a@caseload.test",
            password="x",
            role=User.Role.ADMIN,
        )
        self.outsider = User.objects.create_user(
            username=f"out-{uuid.uuid4().hex[:8]}",
            email="o@caseload.test",
            password="x",
            role=User.Role.STUDENT,
        )

    def _req(self, user, school):
        r = self.factory.get("/staff/discipline/caseload/")
        r.user = user
        r.school = school
        SessionMiddleware(lambda x: None).process_request(r)
        r.session.save()
        setattr(r, "_messages", FallbackStorage(r))
        return r

    def test_renders_for_permissioned_counselor(self):
        resp = counselor_caseload(self._req(self.counselor, self.school))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("Vandersloot", content)
        # Tier label surfaced for the acute student.
        self.assertIn("Tier 2", content)

    def test_admin_tier_passes_without_the_code(self):
        resp = counselor_caseload(self._req(self.admin, self.school))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Vandersloot", resp.content.decode())

    def test_excludes_resolved_stale_tier1_student(self):
        resp = counselor_caseload(self._req(self.counselor, self.school))
        self.assertEqual(resp.status_code, 200)
        # Olden Thistlewood met no inclusion criterion -> not on the caseload.
        self.assertNotIn("Thistlewood", resp.content.decode())

    def test_forbidden_without_permission(self):
        with self.assertRaises(PermissionDenied):
            counselor_caseload(self._req(self.outsider, self.school))

    def test_anonymous_redirects_to_login(self):
        from django.contrib.auth.models import AnonymousUser

        resp = counselor_caseload(self._req(AnonymousUser(), self.school))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"].lower())

    def test_caseload_is_school_scoped(self):
        # Other-school Tier-3 student must not leak into school A's caseload...
        resp_a = counselor_caseload(self._req(self.admin, self.school))
        self.assertEqual(resp_a.status_code, 200)
        self.assertNotIn("Quillfeather", resp_a.content.decode())
        # ...but must be present in their own school's caseload.
        resp_b = counselor_caseload(self._req(self.admin, self.other_school))
        self.assertEqual(resp_b.status_code, 200)
        body_b = resp_b.content.decode()
        self.assertIn("Quillfeather", body_b)
        self.assertNotIn("Vandersloot", body_b)
