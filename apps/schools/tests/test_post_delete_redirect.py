"""Integration tests for post-delete return navigation on super CRUD deletes."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.tests.manager_client import login_manager_control_plane
from apps.siteconfig.models_global_experience import GradingScaleConfig
from apps.siteconfig.models_platform_catalog import RegionConfig


@override_settings(
    ALLOWED_HOSTS=["testserver", "manager.runmycampus.com", "*"],
    ROOT_URLCONF="config.manager_urls",
    OPERATOR_MFA_REQUIRED_ON_MANAGER=False,
)
class SuperCrudPostDeleteRedirectTests(TestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.host = "manager.runmycampus.com"
        self.client = Client(HTTP_HOST=self.host)
        self.user = User.objects.create_superuser(
            username="delete-nav-admin",
            email="delete-nav@example.com",
            password="Test1234!",
        )
        login_manager_control_plane(self.client, self.user, password="Test1234!")
        self.region = RegionConfig.objects.create(
            code="DN",
            name="Delete Nav Region",
            timezone="UTC",
            default_currency="XAF",
            academic_year_start_month=9,
            term_count_per_year=3,
        )

    def test_grading_delete_redirects_to_posted_next(self):
        row = GradingScaleConfig.objects.create(
            region=self.region,
            scale_type="0-20",
            min_score=0,
            max_score=20,
            grade_a_min=16,
            grade_b_min=14,
            grade_c_min=12,
            grade_d_min=10,
            grade_f_min=0,
            display_format="0.00",
        )
        target = reverse("super:grading_list") + "?page=2"
        url = reverse("super:grading_delete", kwargs={"pk": row.pk})
        response = self.client.post(
            url,
            {"confirm": "yes", "next": target},
            HTTP_HOST=self.host,
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], target)
        self.assertFalse(GradingScaleConfig.objects.filter(pk=row.pk).exists())
