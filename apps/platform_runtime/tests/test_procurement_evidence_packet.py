from django.test import SimpleTestCase

from apps.platform_runtime.procurement_packet import build_procurement_packet


class ProcurementEvidencePacketTests(SimpleTestCase):
    def test_procurement_packet_keeps_external_psp_and_certification_claims_honest(
        self,
    ):
        packet = build_procurement_packet(
            tenant_id="school-a",
            external_status={"psp_live_verified": True, "certifications": []},
        )

        self.assertEqual(
            packet["external_dependency_status"]["psp"], "external_required"
        )
        self.assertFalse(packet["honesty"]["claims_soc2"])
        self.assertFalse(packet["honesty"]["claims_iso27001"])
        self.assertFalse(packet["honesty"]["claims_pci"])
        self.assertFalse(packet["honesty"]["psp_live_ready_claim_allowed"])

    def test_full_market_claim_requires_psp_pilots_and_soc2_together(self):
        packet = build_procurement_packet(
            tenant_id="school-a",
            external_status={
                "psp_live_verified": True,
                "psp_evidence_path": "evidence/psp/live-smoke.json",
                "certifications": ["SOC 2 certified"],
                "pilots_live": False,
            },
        )

        self.assertTrue(packet["honesty"]["claims_soc2"])
        self.assertTrue(packet["honesty"]["psp_live_ready_claim_allowed"])
        self.assertFalse(
            packet["honesty"]["full_market_category_defining_claim_allowed"]
        )
        self.assertFalse(
            packet["five_pillar_posture"]["honesty"][
                "full_market_category_defining_claim_allowed"
            ]
        )
