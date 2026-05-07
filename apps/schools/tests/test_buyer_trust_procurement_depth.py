from django.test import SimpleTestCase

from apps.platform_runtime.procurement_packet import build_procurement_packet


class BuyerTrustProcurementDepthTests(SimpleTestCase):
    def test_packet_contains_security_data_isolation_audit_implementation_and_support_sections(self):
        packet = build_procurement_packet(tenant_id="school-a")

        for key in [
            "security_summary",
            "data_handling_summary",
            "tenant_isolation_summary",
            "offline_posture",
            "audit_posture",
            "implementation_process",
            "support_process",
        ]:
            self.assertTrue(packet[key])
        self.assertEqual(packet["external_dependency_status"]["settlement"], "external_required")
