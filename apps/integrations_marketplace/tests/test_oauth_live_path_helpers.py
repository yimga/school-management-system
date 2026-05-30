"""v4.00.92 — Unit tests for ``oauth_live_path_helpers`` (W22 module).

Pure-function helpers shared by Schoology + D2L OAuth live paths:
  * ``decode_oauth2_error_response`` — RFC-6749 § 5.2 error body decoder
  * ``parse_retry_after``           — RFC-7231 § 7.1.3 Retry-After parser
  * ``is_token_expired``            — token-expiry pre-check w/ safety window

All cases are pure-function so we use ``django.test.SimpleTestCase`` (no DB).
"""

from __future__ import annotations

import datetime as _dt

from django.test import SimpleTestCase

from apps.integrations_marketplace import oauth_live_path_helpers as _h


class DecodeOAuth2ErrorResponseTests(SimpleTestCase):
    """Cover the 6 canonical RFC-6749 codes + degenerate inputs."""

    def test_invalid_grant_recognized(self):
        """``invalid_grant`` lands on a stable error_code key."""
        out = _h.decode_oauth2_error_response({
            "error": "invalid_grant",
            "error_description": "bad code or redirect_uri",
        })
        self.assertEqual(out["error_code"], "invalid_grant")
        self.assertEqual(out["error_description"], "bad code or redirect_uri")
        self.assertEqual(out["raw_error"], "invalid_grant")
        self.assertFalse(out["has_error_uri"])

    def test_invalid_client_recognized(self):
        """``invalid_client`` round-trips through the taxonomy."""
        out = _h.decode_oauth2_error_response({"error": "invalid_client"})
        self.assertEqual(out["error_code"], "invalid_client")

    def test_invalid_request_recognized(self):
        """``invalid_request`` round-trips."""
        out = _h.decode_oauth2_error_response({"error": "invalid_request"})
        self.assertEqual(out["error_code"], "invalid_request")

    def test_unauthorized_client_recognized(self):
        """``unauthorized_client`` round-trips + has_error_uri True when uri set."""
        out = _h.decode_oauth2_error_response({
            "error": "unauthorized_client",
            "error_uri": "https://docs.example.com/oauth",
        })
        self.assertEqual(out["error_code"], "unauthorized_client")
        self.assertTrue(out["has_error_uri"])

    def test_unsupported_grant_type_recognized(self):
        """``unsupported_grant_type`` round-trips."""
        out = _h.decode_oauth2_error_response({"error": "unsupported_grant_type"})
        self.assertEqual(out["error_code"], "unsupported_grant_type")

    def test_invalid_scope_recognized(self):
        """``invalid_scope`` round-trips."""
        out = _h.decode_oauth2_error_response({"error": "invalid_scope"})
        self.assertEqual(out["error_code"], "invalid_scope")

    def test_vendor_extension_folds_to_unknown(self):
        """Any non-RFC code (e.g. vendor extension) -> ``upstream_error_unknown``."""
        out = _h.decode_oauth2_error_response({
            "error": "vendor_specific_quota_exhausted",
        })
        self.assertEqual(out["error_code"], "upstream_error_unknown")
        # Raw vendor string preserved for forensic correlation.
        self.assertEqual(out["raw_error"], "vendor_specific_quota_exhausted")

    def test_non_dict_body_string(self):
        """text/plain body lands ``upstream_error_unknown`` w/ raw preserved."""
        out = _h.decode_oauth2_error_response("Service Unavailable")
        self.assertEqual(out["error_code"], "upstream_error_unknown")
        self.assertEqual(out["raw_error"], "Service Unavailable")

    def test_none_body(self):
        """``None`` body -> defaults; never raises."""
        out = _h.decode_oauth2_error_response(None)
        self.assertEqual(out["error_code"], "upstream_error_unknown")
        self.assertEqual(out["raw_error"], "")
        self.assertEqual(out["error_description"], "")
        self.assertFalse(out["has_error_uri"])

    def test_control_chars_stripped_from_description(self):
        """Control chars (0x00-0x1f, 0x7f-0x9f) scrubbed from description."""
        nasty = "valid msg\x00\x01\x02\x7f\x9f trailing"
        out = _h.decode_oauth2_error_response({
            "error": "invalid_grant",
            "error_description": nasty,
        })
        for ch in ("\x00", "\x01", "\x02", "\x7f", "\x9f"):
            self.assertNotIn(ch, out["error_description"])
        self.assertIn("valid msg", out["error_description"])
        self.assertIn("trailing", out["error_description"])


class ParseRetryAfterTests(SimpleTestCase):
    """Cover delta-seconds + HTTP-date + degenerate inputs."""

    def test_delta_seconds(self):
        """Plain integer seconds parses cleanly."""
        self.assertEqual(_h.parse_retry_after("120"), 120.0)

    def test_http_date_future(self):
        """HTTP-date in the future returns positive seconds."""
        # Anchor "now" to a known moment, ask for 10 min in the future.
        now = _dt.datetime(2026, 5, 30, 12, 0, 0, tzinfo=_dt.timezone.utc)
        ra = _h.parse_retry_after("Sat, 30 May 2026 12:10:00 GMT", now=now)
        self.assertIsNotNone(ra)
        self.assertAlmostEqual(ra, 600.0, places=0)

    def test_http_date_in_past_clamped_to_zero(self):
        """Past HTTP-dates clamp to 0 (never negative)."""
        now = _dt.datetime(2026, 5, 30, 12, 0, 0, tzinfo=_dt.timezone.utc)
        ra = _h.parse_retry_after("Sat, 30 May 2026 11:00:00 GMT", now=now)
        self.assertEqual(ra, 0.0)

    def test_none_returns_none(self):
        """Missing header -> None."""
        self.assertIsNone(_h.parse_retry_after(None))

    def test_empty_string_returns_none(self):
        """Empty / whitespace-only header -> None."""
        self.assertIsNone(_h.parse_retry_after(""))
        self.assertIsNone(_h.parse_retry_after("   "))

    def test_malformed_returns_none(self):
        """Garbage string -> None (never raises)."""
        self.assertIsNone(_h.parse_retry_after("not-a-real-value-at-all"))


class IsTokenExpiredTests(SimpleTestCase):
    """Cover fresh / within-safety-window / long-expired / missing inputs."""

    def test_fresh_token_returns_false(self):
        """Token issued 5s ago w/ 3600s expiry -> not expired."""
        now = _dt.datetime(2026, 5, 30, 12, 0, 5, tzinfo=_dt.timezone.utc)
        issued_iso = _dt.datetime(2026, 5, 30, 12, 0, 0,
                                  tzinfo=_dt.timezone.utc).isoformat()
        self.assertFalse(_h.is_token_expired(
            issued_at_iso=issued_iso,
            expires_in_seconds=3600,
            now=now,
        ))

    def test_within_safety_window_returns_true(self):
        """Token expiring in <60s (default safety) -> treat as expired."""
        # Issued 3580s ago, expires_in=3600 -> 20s remaining (<60 safety).
        now = _dt.datetime(2026, 5, 30, 12, 59, 40, tzinfo=_dt.timezone.utc)
        issued_iso = _dt.datetime(2026, 5, 30, 12, 0, 0,
                                  tzinfo=_dt.timezone.utc).isoformat()
        self.assertTrue(_h.is_token_expired(
            issued_at_iso=issued_iso,
            expires_in_seconds=3600,
            now=now,
        ))

    def test_long_expired_returns_true(self):
        """Token issued 2h ago w/ 3600s expiry -> expired."""
        now = _dt.datetime(2026, 5, 30, 14, 0, 0, tzinfo=_dt.timezone.utc)
        issued_iso = _dt.datetime(2026, 5, 30, 12, 0, 0,
                                  tzinfo=_dt.timezone.utc).isoformat()
        self.assertTrue(_h.is_token_expired(
            issued_at_iso=issued_iso,
            expires_in_seconds=3600,
            now=now,
        ))

    def test_missing_inputs_treat_as_expired(self):
        """Missing issued_at_iso -> treat as expired (safer to refresh)."""
        self.assertTrue(_h.is_token_expired(
            issued_at_iso="",
            expires_in_seconds=3600,
        ))
        # Missing/non-positive expires_in -> treat as expired.
        self.assertTrue(_h.is_token_expired(
            issued_at_iso="2026-05-30T12:00:00+00:00",
            expires_in_seconds=0,
        ))
        # Unparseable issued_at_iso -> treat as expired.
        self.assertTrue(_h.is_token_expired(
            issued_at_iso="not-an-iso-date",
            expires_in_seconds=3600,
        ))

    def test_z_suffix_iso_accepted(self):
        """`...Z` ISO suffix is normalized to `+00:00` for fromisoformat."""
        now = _dt.datetime(2026, 5, 30, 12, 0, 5, tzinfo=_dt.timezone.utc)
        # Use Z form deliberately.
        issued_iso = "2026-05-30T12:00:00Z"
        # Should be treated as +00:00 and yield not-expired.
        self.assertFalse(_h.is_token_expired(
            issued_at_iso=issued_iso,
            expires_in_seconds=3600,
            now=now,
        ))
