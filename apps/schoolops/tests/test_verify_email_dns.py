"""Pure-logic tests for the verify_email_dns verdict helpers (no network, no DB)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.schoolops.management.commands.verify_email_dns import (
    evaluate_dkim,
    evaluate_dmarc,
    evaluate_spf,
    evaluate_stray_dkim,
)

DOMAIN = "example.org"


class SpfVerdictTests(SimpleTestCase):
    def test_missing_spf_fails(self):
        r = evaluate_spf([], DOMAIN)
        self.assertFalse(r["passed"])
        self.assertEqual(r["severity"], "critical")

    def test_spf_without_brevo_fails(self):
        r = evaluate_spf(["v=spf1 include:_spf.porkbun.com ~all"], DOMAIN)
        self.assertFalse(r["passed"])
        self.assertIn("spf.brevo.com", r["fix"])

    def test_spf_with_brevo_passes(self):
        r = evaluate_spf(
            ["v=spf1 include:_spf.porkbun.com include:spf.brevo.com ~all"], DOMAIN
        )
        self.assertTrue(r["passed"])

    def test_two_spf_records_fail(self):
        r = evaluate_spf(
            ["v=spf1 include:spf.brevo.com ~all", "v=spf1 include:_spf.porkbun.com ~all"],
            DOMAIN,
        )
        self.assertFalse(r["passed"])
        self.assertIn("exactly one", r["message"])

    def test_non_spf_txt_ignored(self):
        r = evaluate_spf(
            ["google-site-verification=abc", "v=spf1 include:spf.brevo.com ~all"],
            DOMAIN,
        )
        self.assertTrue(r["passed"])


class DkimVerdictTests(SimpleTestCase):
    def test_missing_cname_fails(self):
        r = evaluate_dkim("brevo1", None, DOMAIN)
        self.assertFalse(r["passed"])

    def test_wrong_target_fails(self):
        r = evaluate_dkim("brevo1", "b1.example.onrender.com", DOMAIN)
        self.assertFalse(r["passed"])

    def test_brevo_target_passes(self):
        r = evaluate_dkim("brevo2", "b2.example-org.dkim.brevo.com", DOMAIN)
        self.assertTrue(r["passed"])


class StrayDkimVerdictTests(SimpleTestCase):
    def test_absent_is_good(self):
        r = evaluate_stray_dkim(None, DOMAIN)
        self.assertTrue(r["passed"])

    def test_onrender_target_flagged(self):
        r = evaluate_stray_dkim("school-management-system.onrender.com", DOMAIN)
        self.assertFalse(r["passed"])
        self.assertEqual(r["severity"], "warning")
        self.assertIn("DELETE", r["fix"])

    def test_unrelated_target_tolerated(self):
        r = evaluate_stray_dkim("mail.other.dkim.example.net", DOMAIN)
        self.assertTrue(r["passed"])


class DmarcVerdictTests(SimpleTestCase):
    def test_missing_dmarc_warns(self):
        r = evaluate_dmarc([], DOMAIN)
        self.assertFalse(r["passed"])
        self.assertEqual(r["severity"], "warning")

    def test_monitoring_only_passes_but_suggests_progression(self):
        r = evaluate_dmarc(["v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com"], DOMAIN)
        self.assertTrue(r["passed"])
        self.assertIn("quarantine", r["fix"])

    def test_enforced_policy_info(self):
        r = evaluate_dmarc(["v=DMARC1; p=quarantine; pct=100"], DOMAIN)
        self.assertTrue(r["passed"])
        self.assertEqual(r["severity"], "info")
