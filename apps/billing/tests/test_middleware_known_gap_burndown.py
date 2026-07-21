"""The KNOWN_GAPS burndown: middleware that now actually loads in production.

Companion to ``test_middleware_topology_parity``. That module proves every
base-only middleware is *classified*; this one proves the ten that were safe to
wire are actually wired, and that the one dangerous flag stays safe.

WHY THESE ASSERT ON PARSED SOURCE, NOT ``settings.MIDDLEWARE``
--------------------------------------------------------------
``config/settings.py`` builds MIDDLEWARE at module level and then REPLACES it
inside the ``USE_DJANGO_TENANTS`` branch. Production sets that flag; the test
suite runs on SQLite and takes the BASE branch. So reading the live setting here
would only ever see the dead list and could never catch the drift these tests
exist to catch. Same reasoning as the sibling module.

WHY CSP HAS ITS OWN LOCK
------------------------
``ContentSecurityPolicyMiddleware`` was absent from the production list, so no
CSP header shipped at all -- while a zero-tolerance CI gate kept forcing nonces
into templates for a policy nobody was sending. Wiring it is right; wiring it
ENFORCING is not: ``settings.CSP_ENFORCE`` defaults to ``"1"`` and the policy's
style-src is ``('self',)``, while hundreds of templates still carry inline
``style=``. So the middleware and ``CSP_ENFORCE=0`` must travel together, and
``test_csp_stays_report_only_while_wired`` fails if anyone separates them.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re

from django.test import SimpleTestCase

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SCANNER = _REPO_ROOT / "scripts" / "verify_middleware_topology_parity.py"
_SETTINGS = _REPO_ROOT / "config" / "settings.py"
_RENDER_YAML = _REPO_ROOT / "render.yaml"

_CSP_MIDDLEWARE = "apps.security.csp_middleware.ContentSecurityPolicyMiddleware"

# Wired in the KNOWN_GAPS burndown. Each was verified individually against its
# scanner reason before being mounted; the reason gives the required position.
_NEWLY_WIRED = (
    "corsheaders.middleware.CorsMiddleware",
    "apps.compliance.middleware.ComplianceGuardMiddleware",
    "apps.integrations_marketplace.middleware.TenantEmailBindingMiddleware",
    "apps.platform_runtime.workflow_request_middleware.WorkflowProgressRequestMiddleware",
    "apps.api.middleware_idempotency.IdempotencyKeyMiddleware",
    "apps.accounts.middleware.ManagerTenantPrimarySurfaceBlockMiddleware",
    "apps.siteconfig.middleware.OperatorSiteconfigManagerShellMiddleware",
    "apps.migration_cloud.api.rate_limiting.SoftWarnHeaderMiddleware",
    "apps.siteconfig.middleware.html_no_cache.HtmlNoCacheMiddleware",
    _CSP_MIDDLEWARE,
)


def _load_scanner():
    spec = importlib.util.spec_from_file_location("_mw_burndown", _SCANNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MiddlewareKnownGapBurndownTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.scanner = _load_scanner()
        cls.base, cls.tenants = cls.scanner.collect(_SETTINGS)

    def test_newly_wired_middleware_load_in_production(self):
        tenant_set = set(self.tenants)
        for dotted in _NEWLY_WIRED:
            with self.subTest(middleware=dotted):
                self.assertIn(
                    dotted,
                    tenant_set,
                    f"{dotted} is absent from the tenants MIDDLEWARE, so it does not "
                    "run in production (which takes the USE_DJANGO_TENANTS branch).",
                )

    def test_cors_runs_before_any_response_generating_middleware(self):
        """CORS must be first.

        CommonMiddleware and WhiteNoise can both return a response before the
        chain finishes; a CORS middleware below either of them never gets to
        stamp the headers on those responses.
        """
        self.assertEqual(
            self.tenants[0],
            "corsheaders.middleware.CorsMiddleware",
            "CorsMiddleware must be index 0 of the tenants MIDDLEWARE.",
        )

    def test_cors_is_scoped_to_the_api_surface(self):
        """Unscoped CORS stamps Vary: Origin on every response.

        django-cors-headers defaults CORS_URLS_REGEX to ``^.*$``. Left unset,
        mounting CorsMiddleware fragments CDN cache keys across origins for
        pages that have nothing to do with cross-origin requests.
        """
        source = _SETTINGS.read_text(encoding="utf-8")
        self.assertRegex(
            source,
            r'(?m)^CORS_URLS_REGEX\s*=\s*r?"\^/api/"',
            "CORS_URLS_REGEX must scope CorsMiddleware to the API surface.",
        )

    def test_idempotency_sits_after_authentication(self):
        """Position is load-bearing, not cosmetic.

        Above tenant resolution and auth, the middleware's ``_tenant_key`` /
        ``_user_key`` resolve to 'global' / 'anon'. Two tenants sending the same
        Idempotency-Key to the same path would then replay each other's cached
        response bodies -- a cross-tenant data leak created by mounting a real
        control at the wrong index.
        """
        self.assertLess(
            self.tenants.index("django.contrib.auth.middleware.AuthenticationMiddleware"),
            self.tenants.index("apps.api.middleware_idempotency.IdempotencyKeyMiddleware"),
            "IdempotencyKeyMiddleware must sit AFTER AuthenticationMiddleware so its "
            "keys are tenant- and user-scoped.",
        )

    def test_messages_dependent_middleware_sit_after_message_middleware(self):
        """Both call ``messages.warning``; above MessageMiddleware that raises."""
        message_at = self.tenants.index(
            "django.contrib.messages.middleware.MessageMiddleware"
        )
        for dotted in (
            "apps.accounts.middleware.ManagerTenantPrimarySurfaceBlockMiddleware",
            "apps.siteconfig.middleware.OperatorSiteconfigManagerShellMiddleware",
        ):
            with self.subTest(middleware=dotted):
                self.assertLess(message_at, self.tenants.index(dotted))

    def test_compliance_guard_sits_after_the_school_bridge(self):
        """It reads ``request.school``; above the bridge there is no school."""
        self.assertLess(
            self.tenants.index("apps.schools.middleware.TenantSchemaSchoolBridgeMiddleware"),
            self.tenants.index("apps.compliance.middleware.ComplianceGuardMiddleware"),
        )

    def test_csp_stays_report_only_while_wired(self):
        """CSP must not ship enforcing until the inline-style backlog is real.

        ``settings.CSP_ENFORCE`` defaults to "1", so the middleware enforces
        unless render.yaml says otherwise. With style-src ('self',) and hundreds
        of templates still carrying inline style=, enforcing breaks the product.
        If CSP is wired, CSP_ENFORCE=0 must be set on every service.
        """
        if _CSP_MIDDLEWARE not in set(self.tenants):
            self.skipTest("CSP middleware is not wired; nothing to lock.")
        render = _RENDER_YAML.read_text(encoding="utf-8")
        values = re.findall(r'-\s*key:\s*CSP_ENFORCE\s*\n\s*value:\s*"?([^"\n]+)"?', render)
        self.assertTrue(
            values,
            "ContentSecurityPolicyMiddleware is wired but render.yaml never sets "
            "CSP_ENFORCE. settings.CSP_ENFORCE defaults to '1', so CSP would ship "
            "ENFORCING against templates that still use inline style=.",
        )
        self.assertEqual(
            sorted(set(values)),
            ["0"],
            "CSP_ENFORCE must be '0' (Report-Only) on every service while the "
            "inline-style backlog is open. Retire the backlog first -- and note "
            "that scan_inline_style_off_token does NOT measure it.",
        )

    def test_do_not_add_middleware_are_still_out(self):
        """Regression guard on the four that would cause real harm.

        RequestTimeoutMiddleware runs the chain in a ThreadPoolExecutor whose
        thread-local DB connection carries no search_path, so every tenant query
        would hit the PUBLIC schema. TenantCorsAllowlistMiddleware permanently
        mutates process-global CORS_ALLOWED_ORIGINS, leaking one tenant's origins
        into every later request in that worker. Wiring either is a breach, not a
        fix -- and both look like obvious "gaps" to anyone reading only the diff.
        """
        tenant_set = set(self.tenants)
        for dotted in self.scanner.DO_NOT_ADD:
            with self.subTest(middleware=dotted):
                self.assertNotIn(dotted, tenant_set)
