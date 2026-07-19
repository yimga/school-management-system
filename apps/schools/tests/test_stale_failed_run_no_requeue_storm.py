"""A FAILED run on an ALREADY-PROVISIONED school must not be requeued, forever.

Found in production (2026-07-16) while verifying the provisioning watchdog deploy.

Three tenants (gilead-tech, moja-skola, new-school) each carried a
``status="failed"`` ``tenant_school_provision`` run pinned at ``tenant_schema``,
while the database said the exact opposite: schema present, **322 tables, 1196
applied migrations, is_active=True, phase A + B complete**. The drives had been
killed AFTER the migrate landed but BEFORE ``finalize_run`` could write
"succeeded", so the rows stayed FAILED while the tenants were fully live.

That was harmless only because ``workflow_failed_provision_auto_requeue_sweep``
was a silent no-op: it ordered by ``-updated_at``, a field ``WorkflowRun`` does
not have, so it raised ``FieldError`` into a swallow-all and scanned nothing.
Fixing that ordering (``-started_at``) made the sweep REAL — and exposed that it
has no settled-check, no cooldown, no attempt cap, and never clears the row it
just requeued. Every 600s tick would therefore re-pick the same stale rows and
re-drive three finished tenants: an unbounded migrate storm, caused by making a
broken sweep work.

These tests pin the guard: a settled school is never requeued, and its stale row
is resolved so it leaves the candidate set instead of being reconsidered forever.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.platform_runtime.models import WorkflowRun
from apps.schools.models import School


def _failed_run(school) -> WorkflowRun:
    return WorkflowRun.objects.create(
        workflow_key="tenant_school_provision",
        school_id=str(school.pk),
        status="failed",
        total_steps=5,
        current_step_ordinal=3,
        current_step_name="tenant_schema",
        expected_duration_seconds=600,
        error_summary={
            "type": "TimeoutError",
            "message": "workflow run abandoned: no heartbeat past the stuck threshold",
        },
    )


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class StaleFailedRunOnProvisionedSchoolTests(TestCase):
    def setUp(self):
        # Mirrors prod: live tenant, both phases done, but a FAILED run left behind.
        self.school = School.objects.create(
            name="Gilead Tech",
            slug="gilead-tech-stale",
            subdomain="gilead-tech-stale",
            is_active=True,
            settings={"provisioning": {"phase_a_complete": True, "phase_b_complete": True}},
        )
        self.run = _failed_run(self.school)

    def test_settled_school_is_never_requeued(self):
        from apps.platform_runtime.tasks import (
            workflow_failed_provision_auto_requeue_sweep_task,
        )

        with patch(
            "apps.platform_runtime.workflow_fix_handlers.apply_auto_fix_kind"
        ) as apply_fix, patch(
            "apps.platform_runtime.workflow_autopilot.try_auto_apply_on_failure"
        ) as auto_apply:
            result = workflow_failed_provision_auto_requeue_sweep_task()

        self.assertTrue(result.get("ok"), msg=f"sweep failed: {result}")
        self.assertEqual(
            result.get("requeued"),
            0,
            "a fully-provisioned school must NEVER be re-driven off a stale FAILED row",
        )
        self.assertGreaterEqual(result.get("settled_skipped", 0), 1)
        apply_fix.assert_not_called()
        auto_apply.assert_not_called()

    def test_stale_row_is_resolved_so_it_stops_being_reconsidered(self):
        # Without this the row stays "failed" and is re-picked on EVERY tick --
        # the storm is driven by the row never leaving the candidate set.
        from apps.platform_runtime.tasks import (
            workflow_failed_provision_auto_requeue_sweep_task,
        )

        workflow_failed_provision_auto_requeue_sweep_task()
        self.run.refresh_from_db()
        self.assertEqual((self.run.status or "").lower(), "cancelled")
        self.assertIn("superseded", (self.run.error_summary or {}).get("message", ""))

    def test_sweep_is_idempotent_across_ticks(self):
        from apps.platform_runtime.tasks import (
            workflow_failed_provision_auto_requeue_sweep_task,
        )

        first = workflow_failed_provision_auto_requeue_sweep_task()
        second = workflow_failed_provision_auto_requeue_sweep_task()
        self.assertEqual(first.get("settled_resolved"), 1)
        self.assertEqual(
            second.get("settled_resolved"),
            0,
            "a resolved row must not be re-resolved every tick",
        )
        self.assertEqual(second.get("requeued"), 0)

    def test_retired_row_actually_leaves_the_flight_deck(self):
        """status="cancelled" ALONE does not clear the deck.

        The deck lists status__in=("failed","cancelled") and only hides rows
        carrying the remediation stamp. Without the stamp the operator is left
        staring at a permanent red row for a healthy school -- and because the
        school is settled, _can_requeue_provision is False, so that row renders
        with NO fix button and nothing they can do about it.
        """
        from apps.platform_runtime.tasks import (
            workflow_failed_provision_auto_requeue_sweep_task,
        )
        from apps.platform_runtime.workflow_fix_handlers import workflow_run_is_remediated

        self.assertFalse(workflow_run_is_remediated(self.run))
        workflow_failed_provision_auto_requeue_sweep_task()
        self.run.refresh_from_db()
        self.assertTrue(
            workflow_run_is_remediated(self.run),
            "a retired stale row MUST carry the remediation stamp, else the deck "
            "keeps showing it as an unactionable red item",
        )
        # ...and it must explain itself rather than look like a silent failure.
        self.assertIn(
            "fully provisioned",
            (self.run.suggested_remediation or {}).get("human_action", ""),
        )

    def test_retired_row_offers_no_misleading_fix_button(self):
        from apps.platform_runtime.tasks import (
            workflow_failed_provision_auto_requeue_sweep_task,
        )
        from apps.platform_runtime.workflow_flight_deck_actions import (
            build_operator_actions,
        )
        from apps.platform_runtime.workflow_tracker import serialize_workflow_run

        workflow_failed_provision_auto_requeue_sweep_task()
        self.run.refresh_from_db()
        kinds = [
            a.get("kind")
            for a in build_operator_actions(
                run=self.run, payload=serialize_workflow_run(self.run)
            )
        ]
        self.assertNotIn("apply_fix", kinds)
        self.assertNotIn("requeue_provision", kinds)


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class GenuinelyUnprovisionedSchoolStillRequeuedTests(TestCase):
    """The guard must not silence the case the sweep exists for."""

    def setUp(self):
        self.school = School.objects.create(
            name="Genuinely Broken",
            slug="genuinely-broken",
            subdomain="genuinely-broken",
            is_active=False,
        )
        self.run = _failed_run(self.school)

    def test_unprovisioned_school_is_still_a_candidate(self):
        from apps.platform_runtime.tasks import (
            workflow_failed_provision_auto_requeue_sweep_task,
        )

        result = workflow_failed_provision_auto_requeue_sweep_task()
        self.assertTrue(result.get("ok"), msg=f"sweep failed: {result}")
        self.assertEqual(
            result.get("settled_skipped"),
            0,
            "an inactive, unprovisioned school must NOT be treated as settled",
        )
        self.run.refresh_from_db()
        # A successful requeue may supersede this row (status cancelled + stamp).
        # What must never happen: retiring it as "settled / fully provisioned"
        # while the school is still inactive and unfinished.
        err = (self.run.error_summary or {}).get("message", "")
        human = (self.run.suggested_remediation or {}).get("human_action", "")
        self.assertNotIn(
            "fully provisioned",
            f"{err} {human}",
            "genuinely broken schools must not be retired as settled",
        )
        if (self.run.status or "").lower() == "cancelled":
            self.assertIn("superseded", err.lower())
        else:
            self.assertEqual(
                (self.run.status or "").lower(),
                "failed",
                "a genuinely failed run must stay a candidate for remediation",
            )
