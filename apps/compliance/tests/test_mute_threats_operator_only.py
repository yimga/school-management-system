"""``ThreatDetectionConfig`` is a PLATFORM singleton — only an operator may mute it.

The model has no ``school`` FK and ``is_active`` is ``unique=True``, so there is
exactly one row for the whole platform; ``detect_threats`` returns ``[]`` for
EVERY school while it is muted. ``/compliance/api/mute-threats/`` is mounted on
the tenant urlconf, so gating it on "is this an admin of some school" let one
school's admin suppress brute-force and after-hours alerting for every other
tenant. The gate must be control-plane access.
"""

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.compliance.models_audit import ThreatDetectionConfig
from apps.compliance.views_api import mute_threats
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import RegionConfig


class MuteThreatsIsOperatorOnlyTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            slug="mute-threats-school",
            subdomain="mute-threats-school",
            name="Mute Threats School",
            default_region=self.region,
            timezone=self.region.timezone,
        )
        self.tenant_admin = User.objects.create_user(
            username="mute_threats_tenant_admin",
            password="pass12345",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.tenant_admin,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        self.operator = User.objects.create_superuser(
            username="mute_threats_operator",
            email="operator@example.com",
            password="pass12345",
        )
        ThreatDetectionConfig.objects.all().delete()

    def _post(self, user, duration="24h"):
        request = self.factory.post(
            "/compliance/api/mute-threats/", {"duration": duration}
        )
        request.user = user
        request.school = self.school
        return mute_threats(request)

    def test_operator_can_still_mute(self):
        """Reached-the-code guard: the endpoint works and really writes mute_until.

        Without this, the denial assertion below could pass because the view was
        broken rather than because the gate held.
        """
        response = self._post(self.operator)
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(ThreatDetectionConfig.get_active().mute_until)

    def test_tenant_admin_cannot_mute_the_platform_singleton(self):
        with self.assertRaises(PermissionDenied):
            self._post(self.tenant_admin)
        # And nothing was written: a gate that 403s after the save is not a gate.
        self.assertIsNone(ThreatDetectionConfig.get_active().mute_until)

    def test_tenant_admin_cannot_clear_an_operator_mute(self):
        self._post(self.operator)
        muted_until = ThreatDetectionConfig.get_active().mute_until
        self.assertIsNotNone(muted_until)

        with self.assertRaises(PermissionDenied):
            self._post(self.tenant_admin, duration="clear")
        self.assertEqual(ThreatDetectionConfig.get_active().mute_until, muted_until)


class ThreatDetectionConfigIsOffTheTenantAdminTests(TestCase):
    """The same singleton must not be editable from a school's own /admin/ either.

    ``config/admin.py`` re-homes it onto the platform admin via
    ``TENANT_ADMIN_OPERATOR_ONLY``; this pins that, because the model has no
    ``school`` column and so cannot be caught by the school-field scoping mixin.
    """

    def test_not_registered_on_the_tenant_admin_site(self):
        from config.admin import platform_admin_site, tenant_admin_site

        self.assertNotIn(ThreatDetectionConfig, tenant_admin_site._registry)
        self.assertIn(ThreatDetectionConfig, platform_admin_site._registry)
