"""A paired box is an enabled box — without anyone editing a file on the host.

THE FAILURE THIS PINS. Pairing was built so adopting a box needs nothing but a code on
a screen and an admin clicking approve. Then the box still did not sync, because
``RMC_EDGE_SYNC_ENABLED`` lived in ``deploy/selfhost/.env`` and nobody told the
installer to go and edit a file they cannot even see from the pairing screen. Address
right, credential right, box idle. That is the same shape of silent misconfiguration
pairing exists to end, so these tests pin the rule that replaced it.

The negative here matters as much as the positive: a CLOUD deployment must never be
switched into edge-sync behaviour by a row appearing in a table. ``EdgeCloudBinding``
lives in a SHARED app, so that table exists on the cloud too.
"""
from __future__ import annotations

from django.test import TestCase, override_settings

from apps.sync_engine import edge_enabled


class EdgeEnabledResolutionTests(TestCase):
    def setUp(self):
        edge_enabled.invalidate()
        self.addCleanup(edge_enabled.invalidate)

    def _bind(self, *, base="https://gilead.runmycampus.com", credential="tok"):
        from apps.sync_engine.models_pairing import EdgeCloudBinding

        return EdgeCloudBinding.objects.create(
            operator_base=base, credential=credential, school_slug="gilead-tech"
        )

    # ------------------------------------------------------------------- flag --
    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_the_env_flag_alone_still_enables_sync(self):
        """Every box deployed before pairing existed must keep working untouched."""
        self.assertTrue(edge_enabled.edge_sync_enabled())
        self.assertEqual(edge_enabled.why()["reason"], "RMC_EDGE_SYNC_ENABLED is set")

    @override_settings(RMC_EDGE_SYNC_ENABLED=False, USE_DJANGO_TENANTS=False)
    def test_no_flag_and_no_binding_is_off(self):
        self.assertFalse(edge_enabled.edge_sync_enabled())

    # ---------------------------------------------------------------- pairing --
    @override_settings(RMC_EDGE_SYNC_ENABLED=False, USE_DJANGO_TENANTS=False)
    def test_a_paired_sovereign_box_is_enabled_with_no_flag(self):
        self._bind()
        edge_enabled.invalidate()
        self.assertTrue(edge_enabled.edge_sync_enabled())
        self.assertEqual(
            edge_enabled.why()["reason"], "this box is paired to a cloud tenant"
        )

    @override_settings(RMC_EDGE_SYNC_ENABLED=False, USE_DJANGO_TENANTS=False)
    def test_a_binding_without_a_credential_does_not_count(self):
        """Half a pairing is not a pairing; it would fail on the first request."""
        self._bind(credential="")
        edge_enabled.invalidate()
        self.assertFalse(edge_enabled.edge_sync_enabled())

    @override_settings(RMC_EDGE_SYNC_ENABLED=False, USE_DJANGO_TENANTS=False)
    def test_a_binding_without_an_address_does_not_count(self):
        self._bind(base="")
        edge_enabled.invalidate()
        self.assertFalse(edge_enabled.edge_sync_enabled())

    # ------------------------------------------------------- the cloud is safe --
    @override_settings(
        RMC_EDGE_SYNC_ENABLED=False, USE_DJANGO_TENANTS=True, SINGLE_TENANT=False
    )
    def test_a_cloud_deployment_is_never_flipped_on_by_a_row(self):
        """The whole reason condition 2 carries a deployment-shape check."""
        self._bind()
        edge_enabled.invalidate()
        self.assertFalse(edge_enabled.edge_sync_enabled())
        self.assertEqual(edge_enabled.why()["reason"], "not a sovereign box")

    # ------------------------------------------------------------ memo + bust --
    @override_settings(RMC_EDGE_SYNC_ENABLED=False, USE_DJANGO_TENANTS=False)
    def test_pairing_takes_effect_without_waiting_out_the_memo(self):
        """save_binding busts the memo, so the installer's screen is not lying."""
        from apps.sync_engine import edge_binding

        self.assertFalse(edge_enabled.edge_sync_enabled())  # memoised False
        edge_binding.save_binding(
            operator_base="https://gilead.runmycampus.com",
            credential="tok",
            school_slug="gilead-tech",
        )
        self.assertTrue(
            edge_enabled.edge_sync_enabled(),
            "a freshly paired box was still reporting itself disabled",
        )

    @override_settings(RMC_EDGE_SYNC_ENABLED=False, USE_DJANGO_TENANTS=False)
    def test_unpairing_takes_effect_immediately_too(self):
        from apps.sync_engine import edge_binding

        self._bind()
        edge_enabled.invalidate()
        self.assertTrue(edge_enabled.edge_sync_enabled())
        edge_binding.clear_binding()
        self.assertFalse(edge_enabled.edge_sync_enabled())

    # ------------------------------------------------------------- robustness --
    @override_settings(RMC_EDGE_SYNC_ENABLED=False, USE_DJANGO_TENANTS=False)
    def test_a_broken_lookup_answers_false_rather_than_raising(self):
        """Read on the request path and every scheduler tick — it may never raise."""
        from unittest import mock

        with mock.patch(
            "apps.sync_engine.edge_binding._binding",
            side_effect=RuntimeError("no such table"),
        ):
            edge_enabled.invalidate()
            self.assertFalse(edge_enabled.edge_sync_enabled())


class LateJobRegistrationTests(TestCase):
    """A box adopted at RUNTIME must not wait for a container restart to sync.

    ``ensure_default_jobs`` is one-shot by design. That is right for every job whose
    eligibility is a settings question fixed at import, and wrong for this one: a box
    becomes an edge box when an administrator clicks approve in the cloud, while the
    box is already up and serving.
    """

    def setUp(self):
        edge_enabled.invalidate()
        self.addCleanup(edge_enabled.invalidate)

    @override_settings(RMC_EDGE_SYNC_ENABLED=False, USE_DJANGO_TENANTS=False)
    def test_not_registered_while_the_box_is_unpaired(self):
        from apps.platform_runtime import periodic

        registry = {}
        periodic._maybe_register_edge_sync_job(registry)
        self.assertEqual(registry, {})

    @override_settings(RMC_EDGE_SYNC_ENABLED=False, USE_DJANGO_TENANTS=False)
    def test_registered_once_the_box_is_paired(self):
        from apps.platform_runtime import periodic
        from apps.sync_engine.models_pairing import EdgeCloudBinding

        EdgeCloudBinding.objects.create(
            operator_base="https://gilead.runmycampus.com", credential="tok"
        )
        edge_enabled.invalidate()
        registry = {}
        periodic._maybe_register_edge_sync_job(registry)
        self.assertIn(periodic.EDGE_SYNC_JOB_NAME, registry)

    def test_the_late_hook_is_idempotent_and_cheap_when_present(self):
        from apps.platform_runtime import periodic

        with self.settings(RMC_EDGE_SYNC_ENABLED=True):
            self.assertTrue(periodic.ensure_edge_sync_job_registered())
            self.assertTrue(periodic.ensure_edge_sync_job_registered())

    def test_the_scan_thread_calls_the_late_hook(self):
        """Pinned at the source level: this is the ONLY thing that closes the gap."""
        import inspect

        from apps.platform_runtime import periodic

        source = inspect.getsource(periodic._scan_and_run)
        self.assertIn("ensure_edge_sync_job_registered()", source)
