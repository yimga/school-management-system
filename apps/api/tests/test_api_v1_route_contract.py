"""
Unauthenticated contract for the /api/v1/* surface.

Two properties are asserted:

1. Every named route that is NOT an explicitly-declared public surface must
   reject an anonymous GET (never return 2xx) — no open data leakage.
2. The handful of INTENTIONALLY public routes (`_INTENTIONALLY_PUBLIC`) are
   platform-level surfaces with no tenant PII and no per-user data; the
   frontend / edge / integrations need them before (or without) auth. A route
   may only join that set after confirming its anonymous response carries no
   tenant-scoped or user-scoped data.

The generic sweep builds route kwargs for `<uuid:>`/`<int:>`/`<str:>`/`<slug:>`/
`<path:>` so parametrized routes are actually exercised — previously the
`<str:job_id>` migration-job routes could not be reversed by the sweep and were
silently skipped (their anonymous auth-gating went untested). A focused test
now pins that gating directly.
"""

from __future__ import annotations

import re
import uuid

from django.test import TestCase
from django.urls import reverse

from apps.api.urls_v1 import urlpatterns

_PLACEHOLDER_UUID = uuid.UUID("00000000-0000-0000-0000-000000000042")

# Named routes that INTENTIONALLY serve 2xx to an anonymous caller. Each is a
# platform-level public surface with NO tenant PII and NO per-user data. Adding
# a route here is a deliberate, reviewable security decision — confirm the
# anonymous response body carries no tenant-scoped or user-scoped data first.
_INTENTIONALLY_PUBLIC = frozenset(
    {
        # Static, auth-free API manifest.
        "manifest",
        # /api/v1/runtime/* — edge-cached tenant CONFIG snapshots fronted by the
        # Cloudflare Worker (brand/theme/calendar/grading/flags/defaults). No
        # PII, no per-user data; tenant-scoped reads guard on request.school and
        # return an empty payload with no tenant context (see runtime_endpoints).
        "runtime-calendar",
        "runtime-grading-matrix",
        "runtime-defaults",
        "runtime-site-settings",
        "runtime-feature-flags",
        "runtime-structural-options",
        # Developer-platform vocabularies — platform constants, no tenant data.
        "webhooks-event-types",
        "marketplace-apps",
        "marketplace-scopes",
        # /whoami discovery — returns all-null for an anonymous caller (auth mode
        # + effective scopes only); IntegrationContextView.
        "platform-integration-context",
        # Country-adaptive signup localization pack — country code in, no PII and
        # no tenant context required (country_localization_pack).
        "localization-country-pack",
    }
)


def _kwargs_for_route(pattern_str: str) -> dict:
    """Build placeholder kwargs so a parametrized route can be reversed.

    Handles every path converter this urlconf uses. `str`/`slug`/`path` all
    accept a simple non-empty token, so one placeholder string reverses them.
    """
    kw: dict = {}
    for m in re.finditer(r"<(uuid|int|str|slug|path):(\w+)>", pattern_str):
        typ, name = m.group(1), m.group(2)
        if typ == "uuid":
            kw[name] = _PLACEHOLDER_UUID
        elif typ == "int":
            kw[name] = 1
        else:  # str / slug / path
            kw[name] = "placeholder"
    return kw


class ApiV1RouteContractTests(TestCase):
    """Full v1 named route sweep — extends manifest + spot smoke tests."""

    _allowed_anonymous = frozenset({401, 403, 400, 404, 405, 302, 301, 429})

    def test_named_routes_except_public_do_not_return_2xx_anonymous_get(self):
        failures = []
        for p in urlpatterns:
            name = getattr(p, "name", None)
            if not name or name in _INTENTIONALLY_PUBLIC:
                continue
            pattern_str = str(p.pattern)
            kws = _kwargs_for_route(pattern_str)
            try:
                url = reverse(f"api_v1:{name}", kwargs=kws)
            except Exception:
                try:
                    url = reverse(f"api_v1:{name}")
                except Exception as exc:
                    failures.append(f"{name}: reverse failed: {exc}")
                    continue
            r = self.client.get(url)
            if 200 <= r.status_code < 300:
                failures.append(
                    f"{name} GET {url} -> {r.status_code} (expected non-2xx for anonymous)"
                )
            elif r.status_code not in self._allowed_anonymous:
                failures.append(
                    f"{name} GET {url} -> {r.status_code} (not in allowed set {self._allowed_anonymous})"
                )
        self.assertEqual(
            failures,
            [],
            msg=";\n".join(failures) if failures else "",
        )

    def test_migration_job_routes_reject_anonymous_get(self):
        """The migration-job snapshot + errors-CSV routes are IsAuthenticated —
        an anonymous GET must be rejected (401/403), never served the snapshot.

        The generic sweep skipped these until `<str:job_id>` kwargs were built,
        so their gating had no direct proof; this pins it end-to-end.
        """
        for name in ("migration-job-status", "migration-job-errors-csv"):
            url = reverse(f"api_v1:{name}", kwargs={"job_id": "placeholder-job"})
            r = self.client.get(url)
            self.assertNotIn(
                r.status_code,
                range(200, 300),
                f"{name} served 2xx to an anonymous caller ({r.status_code})",
            )
            self.assertIn(
                r.status_code,
                (401, 403),
                f"{name} must reject anonymous GET with 401/403, got {r.status_code}",
            )
