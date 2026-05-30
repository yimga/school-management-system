"""v4.00.92 — Unit tests for ``lms_connector_sakai`` (W13 scaffold)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.integrations_marketplace import lms_connector_sakai as _sk


class SakaiScaffoldTests(SimpleTestCase):

    def test_is_scaffold_flag_true(self):
        """Sakai is scaffold-only at W13; flag must be True."""
        self.assertTrue(_sk.IS_SCAFFOLD)
        self.assertEqual(_sk.PROVIDER_SLUG, "sakai")
        self.assertTrue(_sk.DEFAULT_AUTHORIZE_URL_SUFFIX.startswith("/"))
        self.assertTrue(_sk.DEFAULT_TOKEN_URL_SUFFIX.startswith("/"))

    def test_oauth_state_round_trip(self):
        """mint -> read round-trips payload + open-redirect defense."""
        token = _sk.mint_oauth_state(
            client_id="cid", return_to="/courses/", nonce="nx",
        )
        payload, reason = _sk.read_oauth_state(token)
        self.assertEqual(reason, "ok")
        self.assertEqual(payload["client_id"], "cid")
        self.assertEqual(payload["return_to"], "/courses/")
        # // -> /.
        token2 = _sk.mint_oauth_state(
            client_id="cid", return_to="//evil", nonce="",
        )
        payload2, _ = _sk.read_oauth_state(token2)
        self.assertEqual(payload2["return_to"], "/")

    def test_push_grade_scaffold_shape(self):
        """Sakai push_grade scaffold returns PUT shape + scaffold reason."""
        out = _sk.push_grade(
            student_external_id="s1",
            course_external_id="c1",
            assignment_external_id="a1",
            score=85.0, max_score=100.0,
        )
        self.assertTrue(out.get("scaffold"))
        self.assertEqual(out.get("reason"), "scaffold_no_outbound_http")
        self.assertEqual(out.get("target_method"), "PUT")
        path = out.get("target_path_suffix", "")
        self.assertIn("c1", path)
        self.assertIn("a1", path)
        self.assertIn("s1", path)
