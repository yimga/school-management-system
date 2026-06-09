from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase

from apps.api.roadmap_extended_views import (
    AtRiskDashboardStubAPI,
    BIAdHocReportStubAPI,
    CertificationBadgeExpiryStubAPI,
    DisputePayoutFlowsStubAPI,
    ExecutiveDashboardStubAPI,
    MLRegistryStubAPI,
    NestedTenancyStubAPI,
    ORToolsTimetablingStubAPI,
    PredictiveEngineStubAPI,
    QuoteToContractStubAPI,
    RedisTenantCacheStubAPI,
    UKTermPresetStubAPI,
)


class RoadmapExtendedTruthTests(SimpleTestCase):
    def test_runtime_backed_endpoints_no_longer_report_stubs(self):
        request = RequestFactory().get("/")
        request.user = get_user_model()(is_staff=True, is_superuser=True)
        classes = [
            QuoteToContractStubAPI,
            BIAdHocReportStubAPI,
            MLRegistryStubAPI,
            ORToolsTimetablingStubAPI,
            DisputePayoutFlowsStubAPI,
            UKTermPresetStubAPI,
            NestedTenancyStubAPI,
            RedisTenantCacheStubAPI,
            PredictiveEngineStubAPI,
            AtRiskDashboardStubAPI,
            ExecutiveDashboardStubAPI,
            CertificationBadgeExpiryStubAPI,
        ]
        for view_class in classes:
            response = view_class.as_view()(request)
            self.assertEqual(response.status_code, 200, view_class.__name__)
            self.assertNotIn(b"code_presence_stub", response.content, view_class.__name__)
