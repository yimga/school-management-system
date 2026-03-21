"""BR-01–BR-10 API smoke tests."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.schools.models import School


User = get_user_model()


class BrNorthstarApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="BR Test",
            slug="br-test",
            subdomain="br-test",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="brstaff",
            email="br@test.edu",
            password="x",
            is_staff=True,
        )

    def _client_with_school(self):
        c = Client()
        c.force_login(self.user)
        session = c.session
        session["school_id"] = str(self.school.pk)
        session.save()
        return c

    def test_slo_targets(self):
        c = Client()
        c.force_login(self.user)
        r = c.get(reverse("api:api-br-slo-targets"))
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("targets", d)
        self.assertEqual(d["targets"]["api_p50_ms"], 800)
        self.assertIn(
            "rum_web_vitals_summary",
            d.get("observability", {}),
        )

    def test_compliance_validate_enrollment_off(self):
        c = Client()
        c.force_login(self.user)
        r = c.post(
            reverse("api:api-br-validate-enrollment"),
            data='{"school_id": "%s", "student_user_id": "x"}' % self.school.pk,
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)

    def test_compliance_validate_enrollment_on(self):
        self.school.settings = {"compliance_live_validation": True}
        self.school.save(update_fields=["settings"])
        c = Client()
        c.force_login(self.user)
        r = c.post(
            reverse("api:api-br-validate-enrollment"),
            data='{"school_id": "%s"}' % self.school.pk,
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 422)
        self.assertTrue(r.json()["errors"])

    def test_migration_diff_preview(self):
        c = Client()
        c.force_login(self.user)
        r = c.post(
            reverse("api:api-br-migration-diff"),
            data='{"csv_a": "a,b\\n1,2", "csv_b": "a,b\\n1,2\\n3,4"}',
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["row_delta"], 1)

    def test_nl_admin_intent(self):
        c = Client()
        u = User.objects.create_superuser("su", "su@test.edu", "pw")
        c.force_login(u)
        r = c.post(
            reverse("api:api-br-nl-admin"),
            data='{"intent": "active_schools_count"}',
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("count", r.json()["data"])

    def test_tenant_registries_effective(self):
        c = Client()
        c.force_login(self.user)
        r = c.get(
            reverse("api:api-br-tenant-registries")
            + "?school_id="
            + str(self.school.pk)
        )
        # Without request.school, staff still gets defaults
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["attendance_codes"])
