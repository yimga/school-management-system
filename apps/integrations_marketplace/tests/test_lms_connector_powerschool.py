"""v4.00.92 — Unit tests for ``lms_connector_powerschool`` (W12 scaffold)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.integrations_marketplace import lms_connector_powerschool as _ps


class PowerSchoolScaffoldTests(SimpleTestCase):

    def test_is_scaffold_flag_true(self):
        """PowerSchool is scaffold-only at W12; flag must be True."""
        self.assertTrue(_ps.IS_SCAFFOLD)
        self.assertEqual(_ps.PROVIDER_SLUG, "powerschool")
        self.assertTrue(_ps.DEFAULT_AUTHORIZE_URL_SUFFIX.startswith("/"))
        self.assertTrue(_ps.DEFAULT_TOKEN_URL_SUFFIX.startswith("/"))

    def test_oauth_state_round_trip(self):
        """mint -> read round-trips payload + open-redirect defense."""
        token = _ps.mint_oauth_state(
            client_id="cid-abc", return_to="/portal/", nonce="n1",
        )
        payload, reason = _ps.read_oauth_state(token)
        self.assertEqual(reason, "ok")
        self.assertEqual(payload["client_id"], "cid-abc")
        self.assertEqual(payload["return_to"], "/portal/")
        # Open-redirect defense.
        token2 = _ps.mint_oauth_state(
            client_id="cid", return_to="//evil.example.com", nonce="",
        )
        payload2, _ = _ps.read_oauth_state(token2)
        self.assertEqual(payload2["return_to"], "/")

    def test_push_grade_scaffold_shape(self):
        """push_grade scaffold returns scaffold_no_outbound_http + POST shape."""
        out = _ps.push_grade(
            student_external_id="s1",
            course_external_id="sch1",
            assignment_external_id="a1",
            score=85.0, max_score=100.0,
        )
        self.assertTrue(out.get("scaffold"))
        self.assertEqual(out.get("reason"), "scaffold_no_outbound_http")
        self.assertEqual(out.get("target_method"), "POST")
        path = out.get("target_path_suffix", "")
        self.assertIn("sch1", path)
        self.assertIn("a1", path)
