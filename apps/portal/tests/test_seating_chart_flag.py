from django.http import Http404
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.portal.views import seating_chart_view
from apps.platform_runtime.helpers import get_platform_site_settings_record


class SeatingChartFlagTests(TestCase):
    """Seating chart graduated from beta (2026-06-27): it is now ENABLED by
    default (models_support backend-flag default = True) and built out into a
    real per-class seating grid. The flag still exists so a tenant can disable
    it, so the gate now defaults on and only the explicit-disable path 404s."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="attendance-admin", password="testpass123"
        )
        self.user.has_feature_permission = lambda code: code == "attendance.manage"

    def _set_flag(self, value):
        site = get_platform_site_settings_record(create=True)
        flags = dict(site.get_backend_feature_flags())
        flags["enable_seating_chart_beta"] = value
        site.apply_feature_control_state(
            backend_feature_flags=flags,
            field_updates={},
        )

    def test_seating_chart_explicitly_disabled_raises_404(self):
        self._set_flag(False)
        request = self.factory.get("/portal/attendance/seating-chart/")
        request.user = self.user

        with self.assertRaises(Http404):
            seating_chart_view(request)

    def test_seating_chart_enabled_renders(self):
        self._set_flag(True)

        request = self.factory.get("/portal/attendance/seating-chart/")
        request.user = self.user
        response = seating_chart_view(request)

        self.assertEqual(response.status_code, 200)
