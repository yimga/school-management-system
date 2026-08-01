"""Every client API route the surface config advertises must exist on the tenant host.

``resolve_api_urls`` reverses ``_API_URL_CATALOG`` against the *request's* urlconf
and, on ``NoReverseMatch``, logs at DEBUG and returns ``""``. Every consuming
client module then does ``if (!url) return;`` — so a route that is declared only
in ``config/urls.py`` (the apex host) is not a visible error on a tenant
subdomain. It is a **silently dead feature**, for every school on the platform.

Four routes were in exactly that state, and each one disabled a real capability
on every tenant host:

* ``set_theme_preference`` — ``theme-preference-bootstrap.js`` skipped its POST,
  so a tenant user's Light/Dark choice never persisted server-side.
* ``api_friction_ingest`` — ``rmc-friction.js`` and ``rmc-layout-health-sentinel.js``
  had nowhere to post, so UX-friction telemetry collected **zero** data from the
  tenant surfaces, which is the entire product.
* ``client_event_capture`` — ``sentry-browser-bridge.js`` dropped browser and
  service-worker error capture on tenant hosts.
* ``api_csrf_token`` — no CSRF refresh endpoint, so a long-lived tenant page could
  not recover a rotated token.

The parity test below is the seal: any future catalog entry must resolve on the
tenant host or be declared host-specific on purpose.
"""

from __future__ import annotations

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse

from apps.siteconfig.platform_surface_config import _API_URL_CATALOG

TENANT_URLCONF = "config.tenant_urls"
APEX_URLCONF = "config.urls"

# Catalog entries that are deliberately NOT on the tenant host. Anything added
# here is a reviewed decision, not a default.
HOST_SPECIFIC_BY_DESIGN: dict[str, str] = {
    # Operator control-plane preferences live on the manager host only; the
    # catalog already resolves this one through MANAGER_URLCONF.
    "control_plane_preferences": "operator control-plane surface, manager host only",
}

# Entries that legitimately exist on the tenant host and nowhere else. This is the
# correct direction for a tenant-owned resource, so it is declared rather than
# "fixed" — but it is declared, so a genuinely accidental asymmetry still fails.
TENANT_ONLY_BY_DESIGN: dict[str, str] = {
    "tenant_domains": "a school manages its own custom domains from its own host",
}


def _reverses(name: str, urlconf: str) -> bool:
    try:
        reverse(name, urlconf=urlconf)
    except NoReverseMatch:
        return False
    except Exception:  # noqa: BLE001 — needs kwargs, so the NAME exists
        return True
    return True


class TenantClientApiRouteParityTests(SimpleTestCase):
    def test_every_catalog_route_resolves_on_the_tenant_host(self):
        missing = [
            f"{key} -> {name}"
            for key, name, hint in _API_URL_CATALOG
            if hint != "manager"
            and key not in HOST_SPECIFIC_BY_DESIGN
            and not _reverses(name, TENANT_URLCONF)
        ]
        self.assertEqual(
            missing,
            [],
            "These client API routes are advertised to tenant pages but do not exist "
            "on the tenant host, so every consuming JS module silently no-ops:\n  "
            + "\n  ".join(missing),
        )

    def test_the_four_regressed_routes_are_present(self):
        """Named explicitly so a bulk urlconf edit cannot quietly drop them again."""
        for name in (
            "api_csrf_token",
            "set_theme_preference",
            "api_friction_ingest",
            "client_event_capture",
        ):
            with self.subTest(route=name):
                self.assertTrue(
                    _reverses(name, TENANT_URLCONF),
                    f"{name} must be reachable on the tenant host",
                )

    def test_tenant_and_apex_agree_on_the_shared_client_surface(self):
        """A route on one host and not the other is a parity bug in one direction."""
        divergent = []
        for key, name, hint in _API_URL_CATALOG:
            if (
                hint == "manager"
                or key in HOST_SPECIFIC_BY_DESIGN
                or key in TENANT_ONLY_BY_DESIGN
            ):
                continue
            on_tenant = _reverses(name, TENANT_URLCONF)
            on_apex = _reverses(name, APEX_URLCONF)
            if on_tenant != on_apex:
                divergent.append(f"{key} ({name}): tenant={on_tenant} apex={on_apex}")
        self.assertEqual(divergent, [], "\n".join(divergent))

    def test_host_specific_exemptions_stay_justified(self):
        catalog_keys = {row[0] for row in _API_URL_CATALOG}
        for source in (HOST_SPECIFIC_BY_DESIGN, TENANT_ONLY_BY_DESIGN):
            for key, reason in source.items():
                with self.subTest(key=key):
                    self.assertIn(key, catalog_keys)
                    self.assertGreater(len(reason), 20, "exemptions need a real reason")

    def test_tenant_only_exemptions_really_are_tenant_only(self):
        """A stale exemption would hide a future parity gap, so prove it still applies."""
        for key in TENANT_ONLY_BY_DESIGN:
            name = next(row[1] for row in _API_URL_CATALOG if row[0] == key)
            with self.subTest(key=key):
                self.assertTrue(_reverses(name, TENANT_URLCONF))
                self.assertFalse(
                    _reverses(name, APEX_URLCONF),
                    f"{key} now exists on apex too — drop it from TENANT_ONLY_BY_DESIGN",
                )
