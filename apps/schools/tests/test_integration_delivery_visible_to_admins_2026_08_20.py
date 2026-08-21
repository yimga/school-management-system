"""A school can configure its own mail server and never send a thing.

``_get_connection_for_send`` takes host / port / credentials from the school's
resolved config but the BACKEND CLASS from the global ``EMAIL_BACKEND``. On an
edge box -- where ``deploy/selfhost/.env.edge.example`` ships
``EMAIL_BACKEND=console`` -- a school's own mail server is never contacted.
The form accepts the settings, the settings are stored, nothing errors, and the
tenant is simply wrong about their own platform.

The decision recorded here is that this is **informational, never a gate**: a
school that has deliberately chosen no email is not broken and must not be told
it is. Only two things raise a flag -- configuration that is being ignored, and
messages empirically stuck.

That second one matters more than it looks. These probes do no network I/O; the
parked-message count IS the outcome measurement, per
``docs/ENGINEERING_STANDARD_PROVE_THE_OUTCOME.md``. A parked message is proof
that delivery is not happening, and it costs one query.

DB-free: the dead-letter count and the SMTP config resolver are both faked.
"""

from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.schools.integration_delivery import (
    DeliveryStatus,
    delivery_problems,
    delivery_statuses,
)

CONSOLE = "django.core.mail.backends.console.EmailBackend"
SMTP = "django.core.mail.backends.smtp.EmailBackend"

TENANT_CFG = {"source": "tenant_school_settings", "host": "mail.school.example"}
ENV_CFG = {"source": "env", "host": "smtp.relay.example"}
NO_HOST_CFG = {"source": "env", "host": ""}


def _probe(*, backend, cfg, parked=0):
    with override_settings(EMAIL_BACKEND=backend), mock.patch(
        "apps.schoolops.email_delivery.get_resolved_smtp_config", return_value=cfg
    ), mock.patch(
        "apps.schools.integration_delivery._parked_email_count", return_value=parked
    ):
        return delivery_statuses(school=None)[0]


class SchoolOwnMailServerIgnoredTests(SimpleTestCase):
    def test_a_school_mail_server_on_a_preview_backend_is_flagged_as_ignored(self):
        status = _probe(backend=CONSOLE, cfg=TENANT_CFG)
        self.assertFalse(status.can_deliver)
        self.assertTrue(status.config_ignored)
        self.assertTrue(status.is_problem)

    def test_the_message_tells_the_admin_their_settings_are_saved(self):
        # The tenant has evidence it should work -- their saved settings. Telling
        # them only "email is broken" invites them to re-enter correct config.
        status = _probe(backend=CONSOLE, cfg=TENANT_CFG)
        self.assertIn("saved", str(status.remedy))
        self.assertIn("not being used", str(status.reason))

    def test_a_platform_with_no_mail_path_is_not_blamed_on_the_school(self):
        status = _probe(backend=CONSOLE, cfg=ENV_CFG)
        self.assertFalse(status.can_deliver)
        self.assertFalse(status.config_ignored)
        self.assertIn("nothing is lost", str(status.remedy))

    def test_a_working_relay_can_deliver(self):
        status = _probe(backend=SMTP, cfg=ENV_CFG)
        self.assertTrue(status.can_deliver)
        self.assertFalse(status.is_problem)

    def test_smtp_without_a_host_cannot_deliver(self):
        self.assertFalse(_probe(backend=SMTP, cfg=NO_HOST_CFG).can_deliver)


class InformNeverBlockTests(SimpleTestCase):
    def test_a_school_that_chose_no_email_raises_nothing(self):
        # The explicit decision: advisory, not a gate. No parked mail and no
        # ignored config means no flag, even though nothing can deliver.
        with override_settings(EMAIL_BACKEND=CONSOLE), mock.patch(
            "apps.schoolops.email_delivery.get_resolved_smtp_config", return_value=ENV_CFG
        ), mock.patch(
            "apps.schools.integration_delivery._parked_email_count", return_value=0
        ):
            self.assertEqual(delivery_problems(school=None), [])

    def test_stuck_messages_always_raise_a_flag(self):
        status = _probe(backend=CONSOLE, cfg=ENV_CFG, parked=42)
        self.assertTrue(status.is_problem)
        self.assertEqual(status.blocked, 42)

    def test_a_backlog_is_reported_even_on_a_healthy_backend(self):
        # A capable backend with a parked backlog means something WAS wrong and
        # the queue has not drained; silence there would hide a real outage tail.
        status = _probe(backend=SMTP, cfg=ENV_CFG, parked=7)
        self.assertTrue(status.can_deliver)
        self.assertTrue(status.is_problem)

    def test_a_probe_that_raises_is_skipped_not_propagated(self):
        import apps.schools.integration_delivery as mod

        def _boom(school=None):
            raise RuntimeError("probe exploded")

        with mock.patch.object(mod, "_PROBES", (_boom,)):
            self.assertEqual(delivery_statuses(school=None), [])

    def test_an_unreadable_dead_letter_table_counts_zero_rather_than_crashing(self):
        import apps.schools.integration_delivery as mod

        with mock.patch("apps.schoolops.models_email_deadletter.EmailDeadLetter") as dl:
            dl.objects.filter.side_effect = RuntimeError("db gone")
            self.assertEqual(mod._parked_email_count(), 0)


class AdminHealthStripTests(SimpleTestCase):
    """The signal must actually reach the strip a tenant admin looks at."""

    IGNORED = DeliveryStatus(
        key="email",
        name="Email",
        can_deliver=False,
        reason="Your mail server is configured but is not being used.",
        remedy="Ask your administrator to switch it to live sending.",
        blocked=42,
        config_ignored=True,
    )

    def _resolve(self, statuses, surface="admin"):
        from apps.schools import tenant_operational_health as toh

        school = mock.Mock(slug="demo", pk=1)
        with mock.patch(
            "apps.schools.fleet_status.resolve_school_fleet_status",
            return_value={"heatmap_tier": "ok", "is_active": True, "fleet_state": "ok"},
        ), mock.patch(
            "apps.schools.integration_delivery.delivery_problems", return_value=statuses
        ), mock.patch.object(
            toh, "_tenant_ops_metrics", return_value={}
        ):
            return toh.resolve_tenant_operational_health(school, surface=surface)

    def _delivery_chips(self, result):
        return [s for s in result["signals"] if s["key"].startswith("delivery_")]

    def test_an_ignored_config_with_a_backlog_reaches_the_admin_strip(self):
        chips = self._delivery_chips(self._resolve([self.IGNORED]))
        self.assertEqual(len(chips), 1)
        self.assertIn("42", chips[0]["label"])
        self.assertEqual(chips[0]["tone"], "warning")

    def test_it_degrades_the_tier_so_it_is_visible_but_never_down(self):
        # Informational by decision: visible, never presented as an outage.
        result = self._resolve([self.IGNORED])
        self.assertEqual(result["tier"], "degraded")

    def test_the_remedy_rides_along_for_richer_surfaces(self):
        chip = self._delivery_chips(self._resolve([self.IGNORED]))[0]
        self.assertTrue(chip["remedy"])
        self.assertTrue(chip["detail"])

    def test_no_delivery_problems_means_no_delivery_chip(self):
        self.assertEqual(self._delivery_chips(self._resolve([])), [])

    def test_parent_and_student_surfaces_are_not_shown_operator_plumbing(self):
        for surface in ("parent", "student"):
            with self.subTest(surface=surface):
                self.assertEqual(
                    self._delivery_chips(self._resolve([self.IGNORED], surface=surface)),
                    [],
                )
