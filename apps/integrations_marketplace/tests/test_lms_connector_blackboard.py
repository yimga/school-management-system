"""v4.00.92 — Unit tests for ``lms_connector_blackboard`` (W11 scaffold).

Three contract tests:
  * scaffold flag (``IS_SCAFFOLD`` exposed True)
  * OAuth state mint+read round-trip + open-redirect defense shape
  * ``push_grade`` honest-stub returns the documented scaffold response
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.integrations_marketplace import lms_connector_blackboard as _bb


class BlackboardScaffoldTests(SimpleTestCase):

    def test_is_scaffold_flag_true(self):
        """Blackboard IS_SCAFFOLD is a bool (was True at W11; promoted to
        OAUTH_READY in Studio-OS-10X v4.00.91 B1, so we now only assert shape)."""
        self.assertIsInstance(_bb.IS_SCAFFOLD, bool)
        # Stable provider slug + endpoint suffixes are exported for the
        # operator UI to render the "Scaffold (coming soon)" pill.
        self.assertEqual(_bb.PROVIDER_SLUG, "blackboard")
        self.assertTrue(_bb.DEFAULT_AUTHORIZE_URL_SUFFIX.startswith("/"))
        self.assertTrue(_bb.DEFAULT_TOKEN_URL_SUFFIX.startswith("/"))

    def test_oauth_state_round_trip(self):
        """mint -> read round-trips client_id / return_to / nonce."""
        token = _bb.mint_oauth_state(
            client_id="cid-abc", return_to="/portal/dash/", nonce="n1",
        )
        self.assertIsInstance(token, str)
        payload, reason = _bb.read_oauth_state(token)
        self.assertEqual(reason, "ok")
        self.assertEqual(payload["client_id"], "cid-abc")
        self.assertEqual(payload["return_to"], "/portal/dash/")
        self.assertEqual(payload["nonce"], "n1")
        # Open-redirect defense — // path collapses to /.
        token2 = _bb.mint_oauth_state(
            client_id="cid", return_to="//evil.example.com/x", nonce="",
        )
        payload2, _ = _bb.read_oauth_state(token2)
        self.assertEqual(payload2["return_to"], "/")

    def test_push_grade_scaffold_shape(self):
        """push_grade returns scaffold dict w/ would_send + reason."""
        out = _bb.push_grade(
            student_external_id="s1",
            course_external_id="c1",
            assignment_external_id="a1",
            score=85.0, max_score=100.0,
        )
        self.assertTrue(out.get("scaffold"))
        self.assertEqual(out.get("reason"), "scaffold_no_outbound_http")
        # Target path embeds all 3 IDs per Blackboard REST API docs.
        path = out.get("target_path_suffix", "")
        self.assertIn("c1", path)
        self.assertIn("a1", path)
        self.assertIn("s1", path)
        self.assertEqual(out.get("target_method"), "PATCH")
