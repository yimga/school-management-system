"""v4.00.92 — Unit tests for ``lms_connector_itslearning`` (W14 scaffold)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.integrations_marketplace import lms_connector_itslearning as _il


class ItslearningScaffoldTests(SimpleTestCase):

    def test_is_scaffold_flag_true(self):
        """Itslearning IS_SCAFFOLD is a bool (was True at W14; promoted to
        OAUTH_READY in Studio-OS-10X v4.00.91 B4, so we now only assert shape)."""
        self.assertIsInstance(_il.IS_SCAFFOLD, bool)
        self.assertEqual(_il.PROVIDER_SLUG, "itslearning")
        # Itslearning uses absolute (cloud-hosted) URLs, not per-instance suffixes.
        self.assertTrue(_il.DEFAULT_AUTHORIZE_URL.startswith("https://"))
        self.assertTrue(_il.DEFAULT_TOKEN_URL.startswith("https://"))

    def test_oauth_state_round_trip(self):
        """mint -> read round-trips payload + open-redirect defense."""
        token = _il.mint_oauth_state(
            client_id="cid", return_to="/courses/", nonce="nx",
        )
        payload, reason = _il.read_oauth_state(token)
        self.assertEqual(reason, "ok")
        self.assertEqual(payload["client_id"], "cid")
        self.assertEqual(payload["return_to"], "/courses/")
        # Open-redirect defense — //x collapses to /.
        token2 = _il.mint_oauth_state(
            client_id="cid", return_to="//evil.example.com", nonce="",
        )
        payload2, _ = _il.read_oauth_state(token2)
        self.assertEqual(payload2["return_to"], "/")

    def test_push_grade_scaffold_shape(self):
        """push_grade scaffold returns POST shape w/ Itslearning REST path."""
        out = _il.push_grade(
            student_external_id="s1",
            course_external_id="c1",
            assignment_external_id="a1",
            score=85.0, max_score=100.0,
        )
        self.assertTrue(out.get("scaffold"))
        self.assertEqual(out.get("reason"), "scaffold_no_outbound_http")
        self.assertEqual(out.get("target_method"), "POST")
        # Itslearning REST API embeds all 3 IDs + "/v1" suffix.
        path = out.get("target_path_suffix", "")
        self.assertIn("/restapi/personal/grades/Save/", path)
        self.assertTrue(path.endswith("/v1"))
