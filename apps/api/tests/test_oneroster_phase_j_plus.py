"""Phase J+: orgs/courses/users, scopes, IP allowlist, synthetic roster."""

import json

from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.academics.models import Department, Subject
from apps.api.oneroster_views import courses, orgs, users
from apps.integrations_marketplace.models import ServiceIntegration
from apps.schools.models import School


class OneRosterPhaseJPlusTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="J+ School",
            slug="jp-school",
            subdomain="jp-school",
            is_active=True,
        )
        ServiceIntegration.objects.create(
            school=self.school,
            service_name="OneRoster district API",
            service_type=ServiceIntegration.ServiceType.OAUTH,
            is_active=True,
            config={"bearer_token": "jp-secret-token"},
        )
        Department.objects.create(
            name="Science", code=f"JP-SCI-{self.school.pk.hex[:8]}", school=self.school
        )
        Subject.objects.create(name="Biology", school=self.school)

    def _auth(self, path_name: str, view_fn):
        url = reverse(path_name) + f"?school_slug={self.school.slug}"
        req = self.factory.get(url, HTTP_AUTHORIZATION="Bearer jp-secret-token")
        return view_fn(req)

    def test_orgs_includes_school_and_department(self):
        resp = self._auth("api:oneroster-orgs", orgs)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        orgs_list = data.get("orgs") or []
        self.assertGreaterEqual(len(orgs_list), 2)

    def test_courses_lists_subjects(self):
        resp = self._auth("api:oneroster-courses", courses)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertGreaterEqual(len(data.get("courses") or []), 1)

    def test_users_merges_students_teachers(self):
        resp = self._auth("api:oneroster-users", users)
        self.assertEqual(resp.status_code, 200)

    def test_scope_denies_teachers_when_students_only(self):
        integ = ServiceIntegration.objects.get(school=self.school)
        integ.config = {**integ.config, "oneroster_scopes": "roster.students"}
        integ.save()
        url = reverse("api:oneroster-teachers") + f"?school_slug={self.school.slug}"
        from apps.api.oneroster_views import teachers

        req = self.factory.get(url, HTTP_AUTHORIZATION="Bearer jp-secret-token")
        resp = teachers(req)
        self.assertEqual(resp.status_code, 403)

    def test_ip_allowlist_blocks(self):
        integ = ServiceIntegration.objects.get(school=self.school)
        integ.config = {**integ.config, "allowed_ips": "10.0.0.1"}
        integ.save()
        from apps.api.oneroster_views import manifest

        url = reverse("api:oneroster-manifest") + f"?school_slug={self.school.slug}"
        req = self.factory.get(
            url, HTTP_AUTHORIZATION="Bearer jp-secret-token", REMOTE_ADDR="192.168.1.1"
        )
        resp = manifest(req)
        self.assertEqual(resp.status_code, 403)

    def test_synthetic_roster_when_flag(self):
        st = dict(self.school.settings or {})
        st["interop_synthetic_roster"] = True
        self.school.settings = st
        self.school.save()
        from apps.api.oneroster_views import students

        url = reverse("api:oneroster-students") + f"?school_slug={self.school.slug}"
        req = self.factory.get(url, HTTP_AUTHORIZATION="Bearer jp-secret-token")
        resp = students(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        users_list = data.get("users") or []
        self.assertTrue(any("syn" in str(u.get("sourcedId", "")) for u in users_list))
