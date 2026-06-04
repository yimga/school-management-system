"""SimpleTestCase coverage for OneRoster write-scope enforcement (no DB)."""
from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase


class OneRosterWriteScopeTests(SimpleTestCase):
    def _req(self, oauth_payload=None):
        req = RequestFactory().put("/api/roster/v1p2/users/x")
        if oauth_payload is not None:
            setattr(req, "_oneroster_oauth2", oauth_payload)
        return req

    def test_static_bearer_no_payload_is_allowed(self):
        from apps.api.oneroster import _require_write_scope

        # No _oneroster_oauth2 attached → legacy/static path, unaffected.
        self.assertIsNone(_require_write_scope(self._req()))

    def test_readonly_oauth_token_blocked(self):
        from apps.api.oneroster import _require_write_scope

        resp = _require_write_scope(self._req({"scopes": ["roster-core.readonly"]}))
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 403)

    def test_createput_oauth_token_allowed(self):
        from apps.api.oneroster import _require_write_scope

        resp = _require_write_scope(
            self._req({"scopes": ["roster-core.readonly", "roster-core.createput"]})
        )
        self.assertIsNone(resp)

    def test_empty_scopes_blocked(self):
        from apps.api.oneroster import _require_write_scope

        resp = _require_write_scope(self._req({"scopes": []}))
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 403)
