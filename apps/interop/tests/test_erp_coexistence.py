from django.test import SimpleTestCase

from apps.interop import erp_coexistence


class ErpCoexistenceTests(SimpleTestCase):
    def test_patterns_non_empty(self):
        pats = erp_coexistence.list_patterns()
        self.assertGreaterEqual(len(pats), 4)
        codes = {p["code"] for p in pats}
        self.assertIn("sap_s4hana", codes)

    def test_sample_envelope(self):
        env = erp_coexistence.sample_webhook_envelope(
            event="student.updated", school_id="abc"
        )
        self.assertEqual(env["event"], "student.updated")
        self.assertEqual(env["school_id"], "abc")
