from django.test import SimpleTestCase

from apps.studio_os.models import ExperienceRegionApproval
from config.admin import platform_admin_site, tenant_admin_site


class ExperienceRegionApprovalAdminBoundaryTests(SimpleTestCase):
    def test_approval_trail_is_operator_only(self):
        self.assertIn(ExperienceRegionApproval, platform_admin_site._registry)
        self.assertNotIn(ExperienceRegionApproval, tenant_admin_site._registry)

    def test_operator_approval_trail_is_read_only(self):
        model_admin = platform_admin_site._registry[ExperienceRegionApproval]

        self.assertFalse(model_admin.has_add_permission(None))
        self.assertFalse(model_admin.has_change_permission(None))
