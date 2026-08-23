"""The orchestration workbench and JSON API must exist on a production host.

``apps.orchestration.urls`` was included ONLY from ``config/urls.py``. That
urlconf is what a dev machine or a bare-IP host resolves to -- production hosts
are routed by ``UrlConfSwitcherMiddleware`` to ``config/tenant_urls.py`` (a
school's subdomain), ``config/manager_urls.py`` (manager.runmycampus.com) or
``config/public_urls.py`` (marketing). So every orchestration route 404'd
everywhere except a developer's laptop: the operator workbench, the retry
action, and all six JSON API endpoints -- the "public JSON API" the module
docstring advertises.

Nothing caught it. `verify_url_name_integrity` UNIONS registered names across
every host urlconf and asks whether each name reverses SOMEWHERE, and these all
do -- in `config.urls`. `scan_hardcoded_dead_paths` asks the same question of
literal paths. A route that resolves on exactly one non-production urlconf
satisfies both.

These tests resolve against the host urlconfs BY NAME rather than through the
test client, because the client picks its urlconf from ``ROOT_URLCONF`` and
would answer for `config.urls` no matter which host it claimed to be.
"""

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, Resolver404, resolve, reverse

MANAGER = "config.manager_urls"
TENANT = "config.tenant_urls"
DEV = "config.urls"

# The six endpoints the module docstring calls the public JSON API.
API_NAMES = [
    ("api_runs_list_or_create", ()),
    ("api_run_detail", (1,)),
    ("api_run_events", (1,)),
    ("api_run_cancel", (1,)),
    ("api_run_retry", (1,)),
    ("api_slo_snapshot", ()),
]


class OrchestrationOperatorSurfaceOnManagerHostTests(SimpleTestCase):
    def test_workbench_reverses_on_the_manager_host(self):
        url = reverse("orchestration:operator_workbench", urlconf=MANAGER)
        self.assertTrue(url.endswith("/workbench/"), url)

    def test_retry_reverses_on_the_manager_host(self):
        reverse("orchestration:retry_run", args=(1,), urlconf=MANAGER)

    def test_workbench_path_actually_resolves_on_the_manager_host(self):
        # reverse() alone would be satisfied by a name registered anywhere in
        # that urlconf; resolve() proves the path is served.
        match = resolve(
            reverse("orchestration:operator_workbench", urlconf=MANAGER),
            urlconf=MANAGER,
        )
        self.assertEqual(match.func.__name__, "operator_workbench")


class OrchestrationApiOnTenantHostTests(SimpleTestCase):
    def test_every_api_endpoint_reverses_on_the_tenant_host(self):
        for name, args in API_NAMES:
            with self.subTest(name=name):
                reverse(f"orchestration_api:{name}", args=args, urlconf=TENANT)

    def test_every_api_endpoint_reverses_on_the_manager_host(self):
        for name, args in API_NAMES:
            with self.subTest(name=name):
                reverse(f"orchestration_api:{name}", args=args, urlconf=MANAGER)

    def test_api_paths_resolve_to_the_api_module_on_the_tenant_host(self):
        url = reverse("orchestration_api:api_runs_list_or_create", urlconf=TENANT)
        match = resolve(url, urlconf=TENANT)
        self.assertEqual(match.func.__name__, "runs_list_or_create")
        self.assertIn(
            "orchestration",
            url,
            "the API must stay under a namespaced prefix, not the tenant root",
        )

    def test_the_operator_workbench_is_absent_from_the_tenant_host(self):
        # require_super_access_with_host would 403 it anyway, but a tenant host
        # has no business advertising the operator UI at all.
        with self.assertRaises(NoReverseMatch):
            reverse("orchestration:operator_workbench", urlconf=TENANT)


class OrchestrationDevHostUnchangedTests(SimpleTestCase):
    def test_dev_urlconf_still_serves_the_whole_surface(self):
        reverse("orchestration:operator_workbench", urlconf=DEV)
        reverse("orchestration:retry_run", args=(1,), urlconf=DEV)
        for name, args in API_NAMES:
            with self.subTest(name=name):
                reverse(f"orchestration_api:{name}", args=args, urlconf=DEV)

    def test_dev_api_paths_are_unchanged(self):
        # The paths a developer already has bookmarked must not move.
        self.assertEqual(
            reverse("orchestration_api:api_runs_list_or_create", urlconf=DEV),
            "/orchestration/api/runs/",
        )
        self.assertEqual(
            reverse("orchestration_api:api_slo_snapshot", urlconf=DEV),
            "/orchestration/api/slo/",
        )

    def test_no_stray_double_mount_on_the_dev_host(self):
        # A second include of the same module under a different prefix would
        # make reverse() ambiguous and quietly change which URL is emitted.
        try:
            match = resolve("/orchestration/api/runs/", urlconf=DEV)
        except Resolver404:  # pragma: no cover - the reverse test covers this
            self.fail("/orchestration/api/runs/ must resolve on the dev urlconf")
        self.assertEqual(match.namespace, "orchestration_api")
