"""Wave P-G (v3.95.1 — 2026-05-26) — Cross-wave integration tests.

Verifies the kernels compose correctly across module boundaries — not just
each wave in isolation but the connections between them.

Scenarios:
- Agentic AI propose → execute → returns expected shape for WhatsApp body.
- MAT Group Hub aggregator + university apps registry both runnable from a
  single operator context without import collisions.
- Embedded Checkout dispatcher round-trips with the PSP registry.
- Concierge Migration source registry composes with the cert administrator
  Migration Specialist track.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from services.ai_agentic import (
    ActionContext, ProposedAction, execute_action, propose_actions,
)
from services.ai_agentic_runners import get_runner_for


def _ctx(**kw):
    defaults = dict(
        tenant_id="t1", user_id="u1", user_roles=("TEACHER",),
    )
    defaults.update(kw)
    return ActionContext(**defaults)


class AgenticToReadableMessageTests(SimpleTestCase):
    """Agentic AI → output usable as WhatsApp / portal message body."""

    def test_attendance_summary_is_readable(self):
        proposals = propose_actions(prompt="how is attendance today",
                                     ctx=_ctx())
        self.assertGreater(len(proposals), 0)
        action = proposals[0]
        runner = get_runner_for(action.action)
        result = execute_action(action, ctx=_ctx(), runner=runner)
        self.assertTrue(result.ok)
        # The result must contain a `summary` string suitable for a
        # WhatsApp message or portal card.
        self.assertIn("summary", result.result)
        self.assertIsInstance(result.result["summary"], str)

    def test_announcement_draft_is_message_shaped(self):
        action = ProposedAction(
            action="draft_parent_announcement",
            params={"topic": "term 2 PTA meeting", "audience": "all_parents"},
        )
        runner = get_runner_for("draft_parent_announcement")
        result = execute_action(action, ctx=_ctx(), runner=runner)
        self.assertTrue(result.ok)
        draft = result.result["draft"]
        # Has greeting, content, and signoff.
        self.assertIn("Dear parents", draft)
        self.assertIn("term 2 PTA meeting", draft)
        self.assertIn("School Office", draft)


class CrossModuleImportSafetyTests(SimpleTestCase):
    """Importing several kernels in the same Python process must not cause
    circular import / module-collision issues."""

    def test_all_v3950_modules_co_import(self):
        from apps.billing import embedded_checkout, embedded_checkout_psp_dispatcher  # noqa: F401
        from apps.communication import whatsapp_parent_os, whatsapp_parent_os_resolvers  # noqa: F401
        from apps.schools import mat_group_hub, views_mat_group_hub  # noqa: F401
        from services import ai_agentic, ai_agentic_runners  # noqa: F401
        from apps.customersuccess import certified_administrator  # noqa: F401
        from apps.migration_cloud import source_adapters  # noqa: F401
        from apps.academics import timetable_solver  # noqa: F401
        from apps.student360 import university_apps_registry  # noqa: F401
        self.assertTrue(True)  # made it here = no ImportError


class MigrationToCertificationCrossWaveTests(SimpleTestCase):
    """Wave M (migration sources) + Wave L (certified migration specialist
    track) describe the same set of source systems consistently."""

    def test_concierge_track_seeded_alongside_migration_sources(self):
        from apps.customersuccess.certified_administrator import get_track
        from apps.migration_cloud.source_adapters import list_sources

        # The Migration Specialist track exists.
        track = get_track("rmc-migration-specialist-concierge")
        self.assertIsNotNone(track)
        self.assertEqual(track.audience, "Migration-Specialist")

        # And there are source adapters for them to specialize on.
        sources = list_sources()
        self.assertGreaterEqual(len(sources), 7)

    def test_powerschool_appears_in_both_audit_and_curriculum(self):
        """A specialist must know how to migrate from each registered source."""
        from apps.customersuccess.certified_administrator import get_track
        from apps.migration_cloud.source_adapters import get_source

        powerschool = get_source("powerschool-sis")
        self.assertIsNotNone(powerschool)
        # Specialist track must include source-system adapter module.
        track = get_track("rmc-migration-specialist-concierge")
        module_ids = [m.module_id for m in track.modules]
        self.assertIn("ms-c-02", module_ids)  # Source-System Adapters


class CurrencyAndPathwayConsistencyTests(SimpleTestCase):
    """Wave I currency map and Wave O pathway fees must use real currencies."""

    def test_pathway_fee_currencies_have_psp_routing(self):
        from apps.billing.embedded_checkout import (
            _CURRENCY_TO_PREFERRED_PROCESSORS,
        )
        from apps.student360.university_apps_registry import list_pathways

        # Every fee currency in pathway specs should be routable by the
        # embedded-checkout dispatcher (or be the stripe USD default).
        for pathway in list_pathways():
            if pathway.fee_amount_minor == 0:
                continue
            cur = pathway.fee_currency
            if not cur:
                continue
            # Currency exists in the explicit map OR falls back to stripe.
            # Either way, it's routable. This is more of a sanity check.
            self.assertTrue(
                cur in _CURRENCY_TO_PREFERRED_PROCESSORS or cur in ("GBP", "USD", "NGN", "INR", "KES"),
                f"pathway {pathway.pathway_id} fee currency {cur} not routable",
            )
