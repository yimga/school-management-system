"""The tenant workflow builder's action palette must be fully dispatchable.

``workflow_registry.ACTION_TYPES`` is served verbatim to tenants by
``siteconfig:workflow_catalog_api``, so every entry in it is a shape a school can
save into a workflow. ``run_actions`` used to drop anything it had no handler
for into an ``else`` branch that logged and appended a result with NO ``error``
key — so an unhandled palette entry (``email``) recorded a CLEAN WorkflowRunLog
while sending nothing at all.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.siteconfig.workflow_engine import run_actions
from apps.siteconfig.workflow_registry import ACTION_TYPES

# Audit-only by definition (workflow_registry: "Audit log only, no side effect"),
# so having no handler is correct for these.
AUDIT_ONLY_ACTION_TYPES = {"log"}


class WorkflowEmailActionTests(SimpleTestCase):
    def test_catalog_email_action_actually_sends(self):
        """The catalog advertises {to, subject, body} with no channel."""
        sent = []

        def _fake_send_email(to_list, subject, body, **kwargs):
            sent.append((list(to_list), subject, body))
            return True

        with patch(
            "apps.communication.notification_service.send_email", _fake_send_email
        ):
            results = run_actions(
                [
                    {
                        "type": "email",
                        "params": {
                            "to": "head@example.test",
                            "subject": "Fees due",
                            "body": "Please settle.",
                        },
                    }
                ],
                {},
            )

        self.assertEqual(len(results), 1)
        # Proves the send path ran, not merely that nothing raised.
        self.assertEqual(sent, [(["head@example.test"], "Fees due", "Please settle.")])
        self.assertEqual(results[0].get("delivered_email"), 1)
        self.assertIsNone(results[0].get("error"))

    def test_unknown_action_type_is_recorded_as_an_error_not_a_clean_run(self):
        results = run_actions([{"type": "no_such_action", "params": {}}], {})

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].get("error"), "unsupported_action_type")

    def test_audit_only_log_action_is_not_an_error(self):
        results = run_actions([{"type": "log", "params": {"message": "hi"}}], {})

        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0].get("error"))

    def test_every_advertised_action_type_is_dispatchable(self):
        """Seal the catalog against the engine, so a future palette entry
        cannot ship without a handler."""
        self.assertIn("email", ACTION_TYPES)  # guard: catalog not silently emptied
        undispatchable = []
        for action_type in ACTION_TYPES:
            if action_type in AUDIT_ONLY_ACTION_TYPES:
                continue
            results = run_actions(
                [{"type": action_type, "params": {}}], {}, dry_run=True
            )
            if results and results[0].get("error") == "unsupported_action_type":
                undispatchable.append(action_type)
        self.assertEqual(
            undispatchable,
            [],
            "workflow_registry.ACTION_TYPES advertises action types that "
            "workflow_engine.run_actions has no handler for",
        )
