from django.http import Http404
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.portal.views import seating_chart_view
from apps.platform_runtime.helpers import get_platform_site_settings_record


class SeatingChartFlagTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="attendance-admin", password="testpass123"
        )
        self.user.has_feature_permission = lambda code: code == "attendance.manage"

    def test_seating_chart_disabled_raises_404(self):
        request = self.factory.get("/portal/attendance/seating-chart/")
        request.user = self.user

        with self.assertRaises(Http404):
            seating_chart_view(request)

    def test_seating_chart_enabled_renders(self):
        site = get_platform_site_settings_record(create=True)
        flags = dict(site.backend_feature_flags or {})
        flags["enable_seating_chart_beta"] = True
        site.backend_feature_flags = flags
        site.save(update_fields=["backend_feature_flags", "updated_at"])

        request = self.factory.get("/portal/attendance/seating-chart/")
        request.user = self.user
        response = seating_chart_view(request)

        self.assertEqual(response.status_code, 200)
