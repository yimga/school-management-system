"""Edge Onboarding Runbook — every command the runbook prescribes must be REAL.

The runbook is only "100% end to end" if every ``manage.py`` command it tells an
operator to run actually resolves to a registered management command. A dead
reference — a command that was renamed or never existed — surfaces on the box as
``Unknown command: '<x>'``, exactly the failure that a mis-named branding command
produced in the field. This test seals that class two ways:

  1. every ``command_template``'s ``manage.py <cmd>`` invocation is registered
     (the primary, copy-pasteable path); and
  2. every command the runbook NAMES in its workaround prose (the fallback an
     operator copy-pastes when the main step can't complete) is registered.

Both use ``django.core.management.get_commands()`` — the same discovery the CLI
uses — so a command that isn't in an INSTALLED_APP is caught here, not on the box.
No DB needed: SimpleTestCase.
"""
from __future__ import annotations

import re

from django.core.management import get_commands
from django.test import SimpleTestCase

from apps.lifecycle.edge_onboarding import EDGE_ONBOARDING_STEPS

# `python manage.py <command>` — capture the command token after manage.py.
_MANAGE_RE = re.compile(r"manage\.py\s+([a-z][a-z0-9_]+)")

# Every management command the runbook NAMES in prose (workaround text) WITHOUT a
# `manage.py` prefix, keyed by the step it belongs to. Kept explicit so adding a new
# prose command reference is a deliberate edit here — and this test then proves it
# is a real, registered command. (Regression: the migrate_identities workaround once
# named the nonexistent 'ensure_admin_user_for_school'.)
# NOTE: only commands the WORKAROUND prose literally names belong here. A step's
# primary command lives in its command_template (covered by the automatic seal
# above), so e.g. seed_baseline's `backfill_country_baseline` is intentionally NOT
# listed — its workaround describes a different remedy (set country_code / configure
# manually) and names no command.
_PROSE_COMMANDS_BY_STEP = {
    "provision_shell": ("provision_sovereign_school", "ensure_showcase_tenant_entitlements"),
    "migrate_staff": ("import_tenant_staff",),
    "migrate_identities": ("ensure_default_tenant_admin",),
    "configure_box_env": ("check_edge_readiness", "run_periodic_jobs"),
    "enable_configure_sync": ("mint_edge_credential",),
    "seed_operational_data": ("import_sovereign_tenant",),
}


class RunbookCommandIntegrityTests(SimpleTestCase):
    def _registered(self) -> set:
        return set(get_commands())

    def test_every_command_template_invocation_is_registered(self):
        registered = self._registered()
        checked = 0
        for step in EDGE_ONBOARDING_STEPS:
            for cmd in _MANAGE_RE.findall(step.command_template):
                checked += 1
                self.assertIn(
                    cmd,
                    registered,
                    f"step {step.key!r} prescribes unknown command {cmd!r} — "
                    f"an operator running this on the box gets 'Unknown command: {cmd}'.",
                )
        # Guard against the parser silently matching nothing (which would make the
        # assertion vacuous): the runbook has several manage.py invocations.
        self.assertGreaterEqual(checked, 6)

    def test_every_prose_referenced_command_is_registered_and_present(self):
        registered = self._registered()
        by_key = {s.key: s for s in EDGE_ONBOARDING_STEPS}
        for key, commands in _PROSE_COMMANDS_BY_STEP.items():
            step = by_key[key]
            for cmd in commands:
                self.assertIn(
                    cmd,
                    registered,
                    f"{key}: workaround names unknown command {cmd!r} — dead reference.",
                )
                self.assertIn(
                    cmd,
                    step.workaround,
                    f"{key}: workaround should name the real command {cmd!r}.",
                )

    def test_no_dead_owner_command_reference(self):
        # The specific regression: the identity fallback must not name the command
        # that never existed, and must name the real owner-mint command.
        by_key = {s.key: s for s in EDGE_ONBOARDING_STEPS}
        workaround = by_key["migrate_identities"].workaround
        self.assertNotIn("ensure_admin_user_for_school", workaround)
        self.assertIn("ensure_default_tenant_admin", workaround)

    def test_verify_step_uses_management_command_not_shell_dash_c(self):
        by_key = {s.key: s for s in EDGE_ONBOARDING_STEPS}
        cmd = by_key["verify_and_sync_gate"].command_template
        self.assertIn("edge_onboarding_verify", cmd)
        self.assertNotIn("shell -c", cmd)
        data = by_key["seed_operational_data"].command_template
        self.assertNotIn("--fresh", data)
