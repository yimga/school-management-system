"""North-star internal APIs: event catalog, wedge playbook, package impact."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.schools.models import School

User = get_user_model()


class NorthStarApiViewsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="NS API",
            slug="ns-api",
            subdomain="ns-api",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="nsstaff",
            email="ns@test.edu",
            password="x",
            is_staff=True,
        )

    def test_event_catalog_includes_provisioning_events(self):
        c = Client()
        c.force_login(self.user)
        r = c.get(reverse("api:api-north-star-event-catalog"))
        self.assertEqual(r.status_code, 200)
        ev = r.json()["events"]
        self.assertIn("provisioning_started", ev)
        self.assertIn("learning_wedge_pack_applied", ev)
        self.assertIn("marketplace_app_installed", ev)
        self.assertIn("celery_task_started", ev)

    def test_wedge_playbook(self):
        c = Client()
        c.force_login(self.user)
        r = c.get(reverse("api:api-north-star-wedge-playbook"))
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("delivery_modes", d)
        self.assertIn("substitute_interop", d)

    def test_package_impact_requires_school(self):
        c = Client()
        c.force_login(self.user)
        r = c.get(reverse("api:api-north-star-package-impact") + "?package_id=foo")
        self.assertEqual(r.status_code, 400)

    def test_package_impact_with_school_no_version(self):
        c = Client()
        c.force_login(self.user)
        r = c.get(
            reverse("api:api-north-star-package-impact")
            + "?package_id=unknown-pkg&school_id=%s" % self.school.pk
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["preview_available"])

    def test_package_impact_preview_when_package_version_exists(self):
        from apps.packages.models import PackageVersion

        PackageVersion.objects.create(
            package_id="demo-impact",
            version="1.0.0",
            payload_sections={"workflow": {"packs": [{"code": "x"}]}},
        )
        c = Client()
        c.force_login(self.user)
        r = c.get(
            reverse("api:api-north-star-package-impact")
            + "?package_id=demo-impact&school_id=%s" % self.school.pk
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["preview_available"])
        self.assertIn("preview", body)
