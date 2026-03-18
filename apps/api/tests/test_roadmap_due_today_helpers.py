import json
from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase

from apps.api.roadmap_due_today_views import CanaryStatusAPI


class RoadmapDueTodayHelperTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_canary_status_defaults_false_when_school_flag_reader_fails(self):
        request = self.factory.get("/api/roadmap/canary-status/")
        request.user = SimpleNamespace(
            is_authenticated=True, is_staff=True, is_superuser=False
        )
        request.school = SimpleNamespace(
            has_feature=lambda _code: (_ for _ in ()).throw(TypeError("bad flag"))
        )

        response = CanaryStatusAPI.as_view()(request)
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["canary_tenant"])
