"""Scheduled jobs that read TENANT tables must visit tenant schemas (2026-09-01).

Found by auditing which management commands touch a TENANT_APP model without switching
schema. 109 of 418 do; almost all are hand-run, and of the three the cloud's deploy
scripts invoke, two are opt-in and default OFF. The set that actually matters turned out
to be neither of those: it is the periodic scheduler, which
``apps/platform_runtime/periodic.py`` drives in 1,411 lines containing zero schema
switches. The codebase already documents the hole one frame away, in
``apps/people/school_batch_service.py``:

    "periodic.run_job calls this with no schema context, i.e. on public. A bare RUNNING
     query therefore raised ProgrammingError every tick and no batch ever advanced."

That job was fixed in place. Two others were not, and both are worse than a stalled
batch advancer because both concern MAIL:

  * ``send_parent_digests`` -- runs daily AND weekly, and decides who is a guardian.
  * ``redrive_dead_letters`` -- holds parked mail, and its contract is NEVER to raise,
    so the schema error is swallowed and the caller is handed a summary of zeros that
    is byte-identical to "the queue is empty".

WHY THESE TESTS SPY ON THE SCHEMA RATHER THAN ON THE DATA. The suite is single-schema,
and so is every sovereign box (USE_DJANGO_TENANTS=0, RLS). In one schema "the wrong
table" does not exist, so a round-trip test passes whether or not the sweep is present
-- exactly as the existing digest tests always have. The only observable difference is
WHERE the read happened, so that is what is asserted.

THE THREE CLASSES BELOW ARE NOT INTERCHANGEABLE, and the split is the point:

  * ``...SweepsEverySchemaTests`` are LOAD-BEARING. Revert the fix and each fails on its
    own AssertionError. They patch only names that predate the fix.
  * ``...InternalSeamTests`` cannot be load-bearing by revert -- they patch seams the fix
    introduces, so on an unfixed tree they die inside mock.patch with AttributeError,
    which proves the method is new and nothing else. They are kept because the budget
    arithmetic is worth pinning, and labelled so a future reader does not mistake their
    red for evidence.
  * ``SingleSchemaBoxIsUntouchedTests`` are CONTROLS and must pass on BOTH trees. An
    earlier draft of this file asserted the new ``schemas=`` counter inside them; that
    made them fail on revert, which quietly destroys their whole value -- a control that
    only holds after the change cannot tell you the change was safe.
"""
from __future__ import annotations

import uuid
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership

_SWEEP = "apps.people.transfer_service.tenant_sweep_schema_names"
_CTX = "django_tenants.utils.schema_context"


class _SchemaSpy:
    """Records the schema names a run entered."""

    def __init__(self):
        self.entered: list[str] = []

    def context(self, name):
        spy = self

        class _Ctx:
            def __enter__(self_inner):
                spy.entered.append(name)
                return self_inner

            def __exit__(self_inner, *exc):
                return False

        return _Ctx()


class _Provisioned:
    def _provision(self, label):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"{label} {uid}", slug=f"{label}-{uid}",
            subdomain=f"{label}{uid}", is_active=True,
        )
        self.user = User.objects.create_superuser(
            username=f"{label}_admin_{uid}", password="Test1234",
            email=f"{label}{uid}@test.com",
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )


class ScheduledJobsSweepEverySchemaTests(_Provisioned, TestCase):
    """LOAD-BEARING. Each of these fails on its own assertion with the fix reverted."""

    def setUp(self):
        self._provision("digest")

    def test_the_digest_visits_every_tenant_schema(self):
        # Reverted: entered == [] -- the command ran once, on whatever schema the
        # connection happened to be holding, which on the cloud is public.
        spy = _SchemaSpy()
        with patch(_SWEEP, return_value=["s_alpha", "s_beta"]), patch(
            _CTX, side_effect=spy.context
        ):
            call_command("send_parent_digests", stdout=StringIO())
        self.assertEqual(spy.entered, ["s_alpha", "s_beta"])

    def test_the_digest_summary_says_how_many_schemas_were_swept(self):
        # A zero that was never looked for must not read like a zero that was.
        out = StringIO()
        spy = _SchemaSpy()
        with patch(_SWEEP, return_value=["s_alpha", "s_beta"]), patch(
            _CTX, side_effect=spy.context
        ):
            call_command("send_parent_digests", stdout=out)
        self.assertIn("schemas=2", out.getvalue())

    def test_one_failing_tenant_does_not_starve_the_others(self):
        # Also the regression test for a defect in the FIRST draft of this fix: the
        # context was built outside the try, so a raising factory escaped the guard.
        spy = _SchemaSpy()
        out = StringIO()

        def _ctx(name):
            if name == "s_bad":
                raise RuntimeError("tenant is broken")
            return spy.context(name)

        with patch(_SWEEP, return_value=["s_bad", "s_good"]), patch(_CTX, side_effect=_ctx):
            call_command("send_parent_digests", stdout=out)
        self.assertEqual(spy.entered, ["s_good"], out.getvalue())
        self.assertIn("schemas_failed=1", out.getvalue())

    def test_the_redrive_visits_every_tenant_schema(self):
        # Patches nothing inside the redrive -- the real pass runs per schema against an
        # empty queue. Reverted: entered == [], the queue read on one arbitrary schema.
        from apps.schoolops import email_delivery

        spy = _SchemaSpy()
        with patch(_SWEEP, return_value=["s_alpha", "s_beta"]), patch(
            _CTX, side_effect=spy.context
        ):
            email_delivery.redrive_dead_letters(limit=50)
        self.assertEqual(spy.entered, ["s_alpha", "s_beta"])


class SweepInternalSeamTests(_Provisioned, TestCase):
    """NOT load-bearing by revert -- these patch seams the fix introduces.

    On an unfixed tree they raise AttributeError inside mock.patch, which says only that
    the method is new. Kept because the shared-budget arithmetic is the one part of this
    change that could go wrong quietly: granting ``--limit`` per schema instead of per
    run turns a 2000-row safety cap into 2000-per-tenant, and nothing downstream would
    report that.
    """

    def setUp(self):
        self._provision("seam")

    def test_the_scan_cap_is_a_whole_run_budget_not_a_per_tenant_grant(self):
        from apps.communication.management.commands import send_parent_digests as mod

        seen = []

        def _record(self_cmd, *, run_cadence, apply, budget, school_id):
            seen.append(budget)
            return {"scanned": 4, "cadence_skipped": 0, "no_email": 0,
                    "eligible": 0, "sent": 0, "empty_skipped": 0, "errored": 0}

        spy = _SchemaSpy()
        with patch(_SWEEP, return_value=["s_a", "s_b", "s_c"]), patch(
            _CTX, side_effect=spy.context
        ), patch.object(mod.Command, "_run_for_schema", _record):
            call_command("send_parent_digests", "--limit", "10", stdout=StringIO())
        self.assertEqual(seen, [10, 6, 2])

    def test_redrive_counts_from_each_schema_are_merged(self):
        from apps.schoolops import email_delivery

        part = {"scanned": 3, "redriven": 2, "still_pending": 1,
                "exhausted": 0, "abandoned": 0, "blocked_no_backend": 0}
        spy = _SchemaSpy()
        with patch(_SWEEP, return_value=["s_alpha", "s_beta"]), patch(
            _CTX, side_effect=spy.context
        ), patch.object(email_delivery, "_redrive_on_current_schema", return_value=part):
            summary = email_delivery.redrive_dead_letters(limit=50)
        self.assertEqual(summary["scanned"], 6)
        self.assertEqual(summary["redriven"], 4)
        self.assertEqual(summary["schemas"], 2)


@override_settings(USE_DJANGO_TENANTS=False)
class SingleSchemaBoxIsUntouchedTests(_Provisioned, TestCase):
    """CONTROLS. These must pass on BOTH the fixed and the unfixed tree.

    ``tenant_sweep_schema_names`` returns ``[None]`` when tenants are off, so a sovereign
    box enters no context and behaves exactly as before. Without these, making the sweep
    unconditional would satisfy every test above and break every box -- silently, in the
    one deployment where the dead-letter queue matters most, since it is what holds mail
    while the box is offline.

    They assert only what is true of both trees. An earlier draft checked the new
    ``schemas=`` counter here and therefore went red on revert, which would have made a
    reverted run look uniformly broken and told us nothing about safety.
    """

    def setUp(self):
        self._provision("box")

    def test_the_digest_attempts_no_schema_switch_on_a_box(self):
        spy = _SchemaSpy()
        with patch(_CTX, side_effect=spy.context):
            call_command("send_parent_digests", stdout=StringIO())
        self.assertEqual(spy.entered, [])

    def test_the_redrive_attempts_no_schema_switch_on_a_box(self):
        from apps.schoolops import email_delivery

        spy = _SchemaSpy()
        with patch(_CTX, side_effect=spy.context):
            email_delivery.redrive_dead_letters(limit=5)
        self.assertEqual(spy.entered, [])

    def test_the_redrive_never_raises_on_a_box(self):
        from apps.schoolops import email_delivery

        summary = email_delivery.redrive_dead_letters(limit=5)
        self.assertIsInstance(summary, dict)

    def test_the_digest_still_runs_end_to_end_on_a_box(self):
        out = StringIO()
        call_command("send_parent_digests", stdout=out)
        self.assertIn("parent_digests", out.getvalue())
        self.assertIn("mode=dry-run", out.getvalue())
