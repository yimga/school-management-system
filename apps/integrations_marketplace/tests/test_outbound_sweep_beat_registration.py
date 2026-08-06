"""Must-fire guards for the three connected-mailbox sweeper beat tasks
(woken 2026-08-05).

Each was a phantom beat entry — the @shared_task lived outside an autodiscovered
tasks.py, so beat looked the name up, found nothing, and the sweep silently never
ran. IntegrationsMarketplaceConfig.ready() now imports the modules so the names
resolve. Because each sweep makes OUTBOUND calls to third-party providers, the
beat wrappers are gated OFF by default; these tests pin both the registration and
the gate (off → no outbound; on → delegates to the real sweep).
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase, override_settings

from config.celery import app

REGISTERED = (
    "integrations_marketplace.refresh_due_oauth_tokens",
    "integrations_marketplace.fetch_due_mailboxes",
    "integrations_marketplace.renew_due_subscriptions",
)


class OutboundSweepBeatRegistrationTests(SimpleTestCase):
    def test_all_three_sweeper_tasks_are_registered(self):
        import apps.integrations_marketplace.token_refresh  # noqa: F401
        import apps.integrations_marketplace.mailbox_fetch  # noqa: F401
        import apps.integrations_marketplace.subscription_renewal  # noqa: F401

        for name in REGISTERED:
            self.assertIn(
                name, app.tasks,
                f"{name} is not registered — its beat entry is a silent no-op",
            )

    @override_settings(INTEGRATIONS_MARKETPLACE_OUTBOUND_SWEEPS_ENABLED=False)
    def test_sweeps_noop_when_gate_off(self):
        from apps.integrations_marketplace import (
            token_refresh,
            mailbox_fetch,
            subscription_renewal,
        )

        with mock.patch.object(token_refresh, "refresh_due_oauth_tokens") as a, \
                mock.patch.object(mailbox_fetch, "fetch_due_mailboxes") as b, \
                mock.patch.object(subscription_renewal, "renew_due_subscriptions") as c:
            r1 = token_refresh.refresh_due_oauth_tokens_task()
            r2 = mailbox_fetch.fetch_due_mailboxes_task()
            r3 = subscription_renewal.renew_due_subscriptions_task()
        a.assert_not_called()
        b.assert_not_called()
        c.assert_not_called()
        for r in (r1, r2, r3):
            self.assertEqual(r[0]["status"], "disabled_outbound_sweeps_gate_off")

    @override_settings(INTEGRATIONS_MARKETPLACE_OUTBOUND_SWEEPS_ENABLED=True)
    def test_sweeps_delegate_when_gate_on(self):
        from apps.integrations_marketplace import (
            token_refresh,
            mailbox_fetch,
            subscription_renewal,
        )

        with mock.patch.object(token_refresh, "refresh_due_oauth_tokens", return_value=["a"]) as a, \
                mock.patch.object(mailbox_fetch, "fetch_due_mailboxes", return_value=["b"]) as b, \
                mock.patch.object(subscription_renewal, "renew_due_subscriptions", return_value=["c"]) as c:
            self.assertEqual(token_refresh.refresh_due_oauth_tokens_task(), ["a"])
            self.assertEqual(mailbox_fetch.fetch_due_mailboxes_task(), ["b"])
            self.assertEqual(subscription_renewal.renew_due_subscriptions_task(), ["c"])
        a.assert_called_once()
        b.assert_called_once()
        c.assert_called_once()
