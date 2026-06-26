from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import RegionConfig


class GradingSettingsViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.region, _ = RegionConfig.objects.get_or_create(
            code="USA",
            defaults={
                "name": "United States",
                "default_language": "en",
                "timezone": "America/New_York",
                "grading_scale": "0-100",
                "default_currency": "USD",
            },
        )
        self.school = School.objects.create(
            name="Grading School",
            slug="grading-school",
            subdomain="grading-school",
            is_active=True,
            default_region=self.region,
            settings={},
        )
        self.admin = User.objects.create_user(
            username="grading-admin",
            email="grading-admin@example.com",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        self.parent = User.objects.create_user(
            username="grading-parent",
            email="grading-parent@example.com",
            password="testpass123",
            role=User.Role.PARENT,
        )
        SchoolMembership.objects.create(
            user=self.parent,
            school=self.school,
            role=User.Role.PARENT,
            is_primary=True,
        )
        self.url = reverse("siteconfig:grading_settings")

    def _bind_school_session(self):
        session = self.client.session
        session["school_id"] = str(self.school.id)
        session.save()

    def test_admin_can_update_grading_and_language(self):
        self.client.force_login(self.admin)
        self._bind_school_session()

        response = self.client.post(
            self.url,
            data={"grading_scale": "0-20", "default_language": "fr"},
        )
        self.assertEqual(response.status_code, 302)

        self.school.refresh_from_db()
        settings = self.school.settings or {}
        self.assertEqual(settings.get("grading_scale"), "0-20")
        self.assertEqual(settings.get("default_language"), "fr")

    def test_non_admin_is_forbidden(self):
        self.client.force_login(self.parent)
        self._bind_school_session()

        response = self.client.post(
            self.url,
            data={"grading_scale": "0-20"},
        )
        self.assertEqual(response.status_code, 403)

    # --- homework -> gradebook toggle -------------------------------------

    def test_admin_can_enable_homework_eval(self):
        self.client.force_login(self.admin)
        self._bind_school_session()

        response = self.client.post(
            self.url, data={"homework_eval_component": "seq1"}
        )
        self.assertEqual(response.status_code, 302)

        self.school.refresh_from_db()
        self.assertEqual(
            (self.school.settings or {}).get("lms_homework_eval_component"), "seq1"
        )

    def test_admin_can_disable_homework_eval(self):
        self.client.force_login(self.admin)
        self._bind_school_session()
        self.school.settings = {"lms_homework_eval_component": "seq1"}
        self.school.save(update_fields=["settings"])

        response = self.client.post(
            self.url, data={"homework_eval_component": "none"}
        )
        self.assertEqual(response.status_code, 302)

        self.school.refresh_from_db()
        self.assertEqual(
            (self.school.settings or {}).get("lms_homework_eval_component"), "none"
        )

    def test_invalid_homework_eval_is_rejected(self):
        self.client.force_login(self.admin)
        self._bind_school_session()
        self.school.settings = {"lms_homework_eval_component": "seq1"}
        self.school.save(update_fields=["settings"])

        response = self.client.post(
            self.url, data={"homework_eval_component": "exam_score"}
        )
        self.assertEqual(response.status_code, 302)

        self.school.refresh_from_db()
        # Unrecognized value is not written; the prior choice is preserved.
        self.assertEqual(
            (self.school.settings or {}).get("lms_homework_eval_component"), "seq1"
        )

    def test_non_admin_cannot_change_homework_eval(self):
        self.client.force_login(self.parent)
        self._bind_school_session()

        response = self.client.post(
            self.url, data={"homework_eval_component": "seq1"}
        )
        self.assertEqual(response.status_code, 403)

        self.school.refresh_from_db()
        self.assertIsNone((self.school.settings or {}).get("lms_homework_eval_component"))

    def test_get_exposes_homework_choices_and_current(self):
        self.client.force_login(self.admin)
        self._bind_school_session()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        choices = response.context["homework_eval_choices"]
        values = [v for v, _ in choices]
        self.assertEqual(values[0], "none")  # Off leads
        for expected in ("seq1", "seq2", "practical"):
            self.assertIn(expected, values)
        self.assertEqual(response.context["current_homework_eval"], "none")
