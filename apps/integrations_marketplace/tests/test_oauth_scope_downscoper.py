"""v4.00.92 — Unit tests for ``oauth_scope_downscoper`` (W18 module).

Pure-function helper that narrows the OAuth scope set per operation so we
don't request more permission than the call actually needs.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.integrations_marketplace import oauth_scope_downscoper as _ds


_SCHOOLOGY_SCOPES = ("read", "write")
_D2L_SCOPES = (
    "core:*:*", "grades:*:read", "grades:*:write", "enrollment:*:read",
)
_CANVAS_SCOPES = (
    "url:GET|/api/v1/courses",
    "url:GET|/api/v1/users",
    "url:POST|/api/v1/courses/:course_id/assignments/:id/submissions",
)


class DownscopeForOperationTests(SimpleTestCase):
    """Cover the documented op taxonomy + safe-fallback paths."""

    def test_push_grade_narrows_to_write_scopes(self):
        """``push_grade`` op -> only write/post/put/delete/patch scopes."""
        out = _ds.downscope_for_operation(
            provider="schoology",
            operation="push_grade",
            default_scopes=_SCHOOLOGY_SCOPES,
        )
        self.assertIn("write", out)
        self.assertNotIn("read", out)

    def test_read_roster_narrows_to_read_scopes(self):
        """``read_roster`` op -> only read/get scopes."""
        out = _ds.downscope_for_operation(
            provider="d2l",
            operation="read_roster",
            default_scopes=_D2L_SCOPES,
        )
        # All matched scopes should contain "read" (or "get").
        for s in out:
            self.assertTrue("read" in s.lower() or "get" in s.lower(),
                            f"non-read scope leaked through: {s!r}")
        # write scope must NOT appear.
        self.assertNotIn("grades:*:write", out)

    def test_unknown_operation_returns_full_default(self):
        """Unknown op -> full default (no downscope, safe fallback)."""
        out = _ds.downscope_for_operation(
            provider="schoology",
            operation="manage_users",
            default_scopes=_SCHOOLOGY_SCOPES,
        )
        self.assertEqual(set(out), set(_SCHOOLOGY_SCOPES))

    def test_canvas_url_scope_matches_post_keyword(self):
        """Canvas URL-encoded scopes carry HTTP verb -> push_grade matches POST."""
        out = _ds.downscope_for_operation(
            provider="canvas",
            operation="push_grade",
            default_scopes=_CANVAS_SCOPES,
        )
        # The POST scope should match the write-class keywords.
        matched_post = [s for s in out if "POST" in s]
        self.assertTrue(matched_post, "POST URL scope did not match write op")

    def test_empty_default_scopes_returns_empty_tuple(self):
        """No defaults provided -> empty tuple (no scopes to narrow)."""
        out = _ds.downscope_for_operation(
            provider="schoology",
            operation="push_grade",
            default_scopes=(),
        )
        self.assertEqual(out, ())
