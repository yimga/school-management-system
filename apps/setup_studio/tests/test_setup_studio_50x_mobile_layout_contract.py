"""Setup Studio 50X — mobile/PWA layout contract markers."""

from django.test import TestCase
from django.template import Context, Template

from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.setup_studio.zero_friction import get_zero_friction_payload


class SetupStudioMobileLayoutTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Mobile School",
            slug="mobile-school",
            subdomain="mobile-school",
            country_code="CM",
            is_active=True,
        )

    def test_strip_has_scroll_policy_and_health_marker(self):
        tpl = Template(
            '{% include "setup_studio/partials/zero_friction_cta_strip.html" %}'
        )
        html = tpl.render(Context({"zero_friction": get_zero_friction_payload(self.school)}))
        self.assertIn('data-rmc-scroll-policy="paginate"', html)
        self.assertIn("data-rmc-setup-health-score", html)
