from django.test import TestCase
from django.urls import reverse


class UrlAliasTests(TestCase):
    def test_student_portal_grades_alias_redirects(self):
        resp = self.client.get("/portal/student-portal/grades/", follow=True)
        # Expect redirect to login since dashboard requires auth
        self.assertEqual(resp.redirect_chain[0][0], reverse("accounts:login") + "?next=/portal/student-portal/grades/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "name=\"username\"")

    def test_admissions_application_status_alias_redirects(self):
        resp = self.client.get("/portal/admissions/application-status/", follow=True)
        self.assertEqual(resp.redirect_chain[0][0], reverse("accounts:login") + "?next=/portal/admissions/application-status/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "name=\"username\"")
