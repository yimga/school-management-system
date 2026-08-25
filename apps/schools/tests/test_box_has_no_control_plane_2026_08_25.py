"""A school's own box must not have an operator control plane at all.

WHAT HAPPENED. A sovereign box was reached at http://10.10.20.137:10000. Because it
was not recognised as a box, it was handed ``config.urls`` -- the DEVELOPER urlconf.
The school, logged in with their own credentials and their own MFA, saw:

* operator chrome: the RunMyCampus wordmark, an ADMIN badge, and a search box
  offering to "Search tenants, incidents, commands";
* /super/ resolving to a Manager dashboard that said "You do not have read access
  for the Super module" -- and offered a **Request access** button, into the control
  plane;
* every single page hard-redirected to My profile, because the account scored below
  the ADMIN security minimum and the hard redirect is meant for operator surfaces;
* logout among those pages, so signing out was impossible.

The whole of that traced to ONE env var being absent, which is not a tolerable
amount of rope. These tests hold two independent locks:

1. the box is recognised from any marker it actually carries, not one people have
   to remember, and a hosted deployment can never be mistaken for a box;
2. even if lock 1 were wrong, the control-plane routes are not mounted on a box, so
   /super/ is a 404 -- and a 404 cannot offer anybody a Request-access button.
"""

from __future__ import annotations



from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.schools.middleware import is_sovereign_single_tenant_box


class BoxRecognitionTests(SimpleTestCase):
    """Recognised from what a box carries, not from what somebody remembered."""

    def test_the_compose_default_alone_is_enough(self):
        # deploy/selfhost/docker-compose.yml sets ENVIRONMENT=selfhost on the shared
        # app anchor, so every box carries this without anyone doing anything.
        with override_settings(
            RMC_IS_SELFHOST_BOX=True,
            RMC_IS_CLOUD_DEPLOYED=False,
            USE_DJANGO_TENANTS=False,
        ):
            self.assertTrue(is_sovereign_single_tenant_box())

    def test_the_legacy_flag_alone_still_works(self):
        # An existing box that sets only SINGLE_TENANT must not regress.
        with override_settings(
            RMC_IS_SELFHOST_BOX=False,
            RMC_IS_CLOUD_DEPLOYED=False,
            SINGLE_TENANT=True,
            USE_DJANGO_TENANTS=False,
        ):
            self.assertTrue(is_sovereign_single_tenant_box())

    def test_a_plain_developer_machine_is_not_a_box(self):
        with override_settings(
            RMC_IS_SELFHOST_BOX=False,
            RMC_IS_CLOUD_DEPLOYED=False,
            SINGLE_TENANT=False,
            USE_DJANGO_TENANTS=False,
        ):
            self.assertFalse(is_sovereign_single_tenant_box())

    def test_a_hosted_deployment_is_never_a_box_even_with_the_flag_set(self):
        # The flag can leak: copied into a shared .env, inherited from a template,
        # set while debugging. Without this exclusion the CLOUD would be routed to
        # config.tenant_urls and serve every operator a single-school surface.
        with override_settings(
            RMC_IS_SELFHOST_BOX=False,
            RMC_IS_CLOUD_DEPLOYED=True,
            SINGLE_TENANT=True,
            USE_DJANGO_TENANTS=False,
        ):
            self.assertFalse(is_sovereign_single_tenant_box())

    def test_django_tenants_wins_over_everything(self):
        with override_settings(
            RMC_IS_SELFHOST_BOX=True,
            RMC_IS_CLOUD_DEPLOYED=False,
            SINGLE_TENANT=True,
            USE_DJANGO_TENANTS=True,
        ):
            self.assertFalse(is_sovereign_single_tenant_box())


class DerivationTests(SimpleTestCase):
    """The derivation itself, as a pure function.

    Deliberately not by reloading config.settings: that trips the production secret
    guards and leaves a re-executed settings module behind for every test that runs
    afterwards. The rule lives in config/deployment_kind.py precisely so it can be
    asserted directly.
    """

    def _derive(self, cloud=False, **env):
        from config.deployment_kind import selfhost_box_from_env

        return selfhost_box_from_env(env, cloud)

    def test_the_compose_label_alone_derives_a_box(self):
        self.assertTrue(self._derive(ENVIRONMENT="selfhost"))

    def test_the_legacy_flag_alone_derives_a_box(self):
        for spelling in ("1", "true", "TRUE", "yes", "on"):
            with self.subTest(spelling=spelling):
                self.assertTrue(self._derive(SINGLE_TENANT=spelling))

    def test_nothing_set_is_not_a_box(self):
        self.assertFalse(self._derive())
        self.assertFalse(self._derive(ENVIRONMENT="", SINGLE_TENANT=""))

    def test_a_nonsense_value_is_not_a_box(self):
        self.assertFalse(self._derive(SINGLE_TENANT="banana", ENVIRONMENT="production"))

    def test_hosted_beats_every_selfhost_marker(self):
        # "A label must not route" -- and here it specifically must not turn the
        # cloud into an appliance, however the labels arrived.
        self.assertFalse(
            self._derive(cloud=True, ENVIRONMENT="selfhost", SINGLE_TENANT="1")
        )

    def test_the_real_settings_use_this_helper(self):
        # So the rule cannot be reimplemented inline later and drift.
        import inspect

        import config.settings as settings_module

        source = inspect.getsource(settings_module)
        self.assertIn("selfhost_box_from_env(os.environ", source)


class ControlPlaneIsNotMountedTests(SimpleTestCase):
    """The second lock: routes that do not exist cannot be reached by any mistake."""

    def test_the_predicate_catches_every_super_route(self):
        import config.urls as urls_module

        from django.urls import path

        for route in ("super/", "super/migration/", "super/feedback/"):
            with self.subTest(route=route):
                entry = path(route, lambda request: None)
                self.assertTrue(urls_module.is_control_plane_pattern(entry))

    def test_the_predicate_catches_operator_namespaces(self):
        import config.urls as urls_module

        for namespace in urls_module.CONTROL_PLANE_NAMESPACES:
            with self.subTest(namespace=namespace):
                entry = mock.Mock(pattern="anything/", namespace=namespace)
                self.assertTrue(urls_module.is_control_plane_pattern(entry))

    def test_it_does_not_catch_ordinary_school_routes(self):
        import config.urls as urls_module

        from django.urls import path

        for route in ("academics/", "portal/", "authentication/", "superb-idea/"):
            with self.subTest(route=route):
                entry = path(route, lambda request: None)
                entry.namespace = None
                self.assertFalse(urls_module.is_control_plane_pattern(entry))

    def test_a_new_super_route_is_covered_without_anyone_remembering(self):
        # Filtered by prefix, not by an enumerated list, so a /super/ route added
        # years from now is caught by the same lock.
        import config.urls as urls_module

        from django.urls import path

        entry = path("super/something-invented-later/", lambda request: None)
        self.assertTrue(urls_module.is_control_plane_pattern(entry))

    def test_the_developer_urlconf_still_has_its_control_plane(self):
        # The seal must not cost a developer their tools.
        import config.urls as urls_module

        mounted = [
            entry
            for entry in urls_module.urlpatterns
            if urls_module.is_control_plane_pattern(entry)
        ]
        if getattr(urls_module.settings, "RMC_IS_SELFHOST_BOX", False):
            self.assertEqual(mounted, [])
        else:
            self.assertTrue(mounted, "developer urlconf lost its control plane")

    def test_tenant_urls_never_mounted_the_control_plane_in_the_first_place(self):
        import config.tenant_urls as tenant_urls

        offenders = [
            str(entry.pattern)
            for entry in tenant_urls.urlpatterns
            if str(getattr(entry, "pattern", "") or "").startswith("super/")
        ]
        self.assertEqual(offenders, [])


class ReadinessSaysSoTests(SimpleTestCase):
    """A box that would serve the operator surface has to announce it."""

    def _run(self, appliance=True):
        """Run the readiness check, optionally as an appliance.

        ``RMC_EDGE_TLS_MODE`` present in the environment is what marks this process
        as an appliance at all. It is deliberately independent of the recognition
        markers being checked: keying the check off those would be circular, since
        a box that is not recognised is exactly the box that has to be told.
        """
        import os
        from io import StringIO

        from django.core.management import call_command

        env = {"RMC_EDGE_TLS_MODE": "selfsigned"} if appliance else {}
        out = StringIO()
        with mock.patch.dict(os.environ, env, clear=False):
            if not appliance:
                os.environ.pop("RMC_EDGE_TLS_MODE", None)
            try:
                call_command("check_edge_readiness", stdout=out, stderr=out)
            except SystemExit:
                pass
            except Exception:  # noqa: BLE001 - other findings are not the subject here
                pass
        return out.getvalue()

    def test_an_unrecognised_box_is_a_failure_not_a_warning(self):
        with override_settings(
            RMC_IS_SELFHOST_BOX=False,
            RMC_IS_CLOUD_DEPLOYED=False,
            SINGLE_TENANT=False,
            USE_DJANGO_TENANTS=False,
        ):
            output = self._run()
        self.assertIn("operator URL surface", output)
        self.assertIn("[FAIL]", output)

    def test_a_recognised_box_reports_the_clean_state(self):
        with override_settings(
            RMC_IS_SELFHOST_BOX=True,
            RMC_IS_CLOUD_DEPLOYED=False,
            USE_DJANGO_TENANTS=False,
        ):
            output = self._run()
        self.assertIn("sovereign single-school box", output)

    def test_a_developer_machine_is_told_nothing_about_this(self):
        # A dev machine serves config.urls on purpose. Reporting that as a finding
        # would make --strict unusable anywhere except on a box, and a check that
        # cries wolf everywhere is one people learn to skip.
        with override_settings(
            RMC_IS_SELFHOST_BOX=False,
            RMC_IS_CLOUD_DEPLOYED=False,
            SINGLE_TENANT=False,
            USE_DJANGO_TENANTS=False,
        ):
            output = self._run(appliance=False)
        self.assertNotIn("operator URL surface", output)
        self.assertNotIn("sovereign single-school box", output)
