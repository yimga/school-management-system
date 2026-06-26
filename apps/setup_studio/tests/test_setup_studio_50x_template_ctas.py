"""Setup Studio 50X — template CTA strip."""

from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.registries.models import CountryRegistry
from apps.schools.models import School, SchoolMembership


class SetupStudioTemplateCTAsTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Tpl School",
            slug="tpl-school",
            subdomain="tpl-school",
            country_code="CM",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="tpl_admin",
            password="testpass123",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role=User.Role.ADMIN, is_primary=True
        )

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_zero_friction_partial_renders_ctas(self):
        from django.template import Context, Template

        from apps.setup_studio.zero_friction import get_zero_friction_payload

        tpl = Template(
            '{% include "setup_studio/partials/zero_friction_cta_strip.html" %}'
        )
        html = tpl.render(Context({"zero_friction": get_zero_friction_payload(self.school)}))
        self.assertIn('data-rmc-zero-friction="1"', html)
        self.assertIn("Use recommended setup", html)
        self.assertIn("What is blocking launch?", html)
