from django.test import TestCase
from django.urls import reverse


class UrlAliasTests(TestCase):
    def test_student_portal_grades_alias_redirects(self):
        resp = self.client.get("/portal/student-portal/grades/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("portal:parent_dashboard"))

    def test_admissions_application_status_alias_redirects(self):
        resp = self.client.get("/portal/admissions/application-status/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("portal:parent_dashboard"))
