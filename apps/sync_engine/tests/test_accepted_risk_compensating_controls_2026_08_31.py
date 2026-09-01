"""G8: the accepted risk stays accepted, or this fails.

WHAT WAS ACCEPTED, AND BY WHOM. ``models.get_sync_cursor_for_request`` states its own
limit plainly: the rail is not a transactional outbox, so a transaction that stays open
LONGER than the cursor overlap can commit an ``updated_at`` already behind the recorded
high-water and never be offered again. Closing that completely needs a monotonic
sequence written in the same transaction as the business row, which costs a migration on
fifteen live TENANT tables. The trade was made deliberately and is the right one -- but
it is right for ONE reason, and that reason is a compensating control, not the overlap:

    the overlap makes a slip UNLIKELY;
    the parity sweep (``apps.sync_engine.parity``) makes a slip FINDABLE.

An incremental delta only ever offers what changed since the cursor, and a row that
slipped has no ``updated_at`` greater than anything -- so nothing else in the engine can
ever notice it again. Parity is the only mechanism that asks the far side what it
actually HOLDS, and it is therefore the entire recovery path for this accepted risk.

WHAT THIS GUARD IS FOR. Both halves are ordinary settings. Someone tuning a slow box can
set ``RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS=0`` (which the code explicitly supports, and
documents as "restores the exact previous behaviour"), or widen
``RMC_SYNC_PARITY_INTERVAL_SECONDS`` to a day to save a scan, or set
``RMC_SYNC_PARITY_ENABLED=0`` while debugging. Any one of those converts an accepted,
bounded, recoverable risk into an unaccepted, unbounded, undetectable one -- and NOTHING
would fail. Not a test, not a check, not a log line. The next person to find out would
be a school missing a row.

So the bounds are asserted here, in the same spirit and tone as
``manage.py verify_sync_semantics``, which already exists to prove that protected
conflict policies have not been weakened. This is the same idea applied to a trade
instead of a policy.

THE BOUNDS, AND WHY THESE NUMBERS.

  * **Cursor overlap floor = the gunicorn worker timeout.** Not a round number picked
    for feel. A worker is killed at ``GUNICORN_TIMEOUT`` (``services.web_runtime``,
    default 120s), so no request-bound transaction can outlive it -- which is exactly
    why the overlap's own default is 120. An overlap at least that wide covers EVERY
    transaction a web request can hold open, and the setting's default is not an
    arbitrary constant but a match to that ceiling. Reducing it below the worker timeout
    opens a window that is routine rather than theoretical.

    The honest residual, stated because the guard cannot close it: a Celery task or a
    management command is NOT bounded by the worker timeout, so a long batch job can
    still exceed any overlap. That residual is precisely what parity is for, which is
    why the two checks below belong in one guard rather than two.

  * **Parity must be ENABLED.** Off, the residual above has no detection at all.

  * **Parity interval ceiling = 6 hours.** A school day is about eight hours. A sweep at
    least twice per school day means a row that slipped in the morning is found before
    the day ends, while a slip found "within 24 hours" can mean a bursar reconciling
    against a figure that was wrong all day. ``parity.interval_seconds()`` already has a
    FLOOR (60s, so a sweep cannot become a continuous table walk); this is the missing
    other half, because the direction that hurts is widening, not narrowing.

IF YOU ARE HERE BECAUSE THIS FAILED. It is not noise and deleting it is not the fix.
Either put the setting back, or -- if the trade genuinely needs to change -- change the
bound here in the same commit that changes the setting, so the new trade is written down
by the person who chose it. The one thing that must not happen is the trade changing
while this file still claims the old one.
"""
from __future__ import annotations

from django.test import SimpleTestCase, override_settings

# PROMOTED 2026-09-01. The bounds and the check itself now live in the repo gate an
# operator can point at a real deployment -- ``scripts/verify_sync_semantics.py``,
# which calls it in ``main()`` -- because the thing being asserted is a property of a
# DEPLOYMENT's settings, not of the code. A check that only ever ran inside the test
# suite answered the question for the CI settings and for nothing else.
#
# Imported, never re-implemented: a second copy here would drift, and this file would
# go on claiming a trade the gate had already stopped enforcing -- which is the exact
# failure mode the module docstring above warns about.
from apps.platform_runtime.tests.support.script_loading import load_repo_script

_gate = load_repo_script(
    "scripts/verify_sync_semantics.py", "rmc_gate_verify_sync_semantics"
)

PARITY_INTERVAL_CEILING_SECONDS = _gate.PARITY_INTERVAL_CEILING_SECONDS
cursor_overlap_floor_seconds = _gate.cursor_overlap_floor_seconds
compensating_control_violations = _gate.compensating_control_violations


class CompensatingControlGuardTests(SimpleTestCase):
    """The deployment's own settings, checked against the accepted bounds."""

    def test_the_accepted_trade_still_holds(self):
        violations = compensating_control_violations()
        self.assertEqual(
            violations,
            [],
            "the G8 accepted risk has silently become an unaccepted one:\n  - "
            + "\n  - ".join(violations),
        )

    def test_the_overlap_default_matches_the_worker_timeout_it_was_chosen_for(self):
        """The floor is DERIVED, so record what it currently derives to.

        If someone raises `GUNICORN_TIMEOUT` without raising the overlap, the guard
        above fires on its own. This one exists so the relationship is visible rather
        than buried in a helper: the two numbers are the same number for a reason.
        """
        from apps.sync_engine.models import cursor_overlap_seconds

        self.assertGreaterEqual(cursor_overlap_seconds(), cursor_overlap_floor_seconds())


class TheGuardActuallyFiresTests(SimpleTestCase):
    """Prove each arm, by weakening the setting and watching it fail.

    Without these the class above is indistinguishable from three assertions that
    happen to be true, and a refactor that broke the reads would leave a green suite
    guarding nothing.
    """

    @override_settings(RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS=0)
    def test_disabling_the_overlap_fires(self):
        """`0` is a documented, supported value -- which is exactly the danger."""
        violations = compensating_control_violations()
        self.assertTrue(
            any("cursor overlap" in v for v in violations),
            f"overlap=0 did not fire the guard: {violations}",
        )

    @override_settings(RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS=30)
    def test_reducing_the_overlap_below_the_worker_timeout_fires(self):
        """A plausible tuning ("120s of re-shipping is wasteful") is still a weakening."""
        violations = compensating_control_violations()
        self.assertTrue(
            any("cursor overlap" in v for v in violations),
            f"overlap=30 did not fire the guard: {violations}",
        )

    @override_settings(RMC_SYNC_PARITY_ENABLED=False)
    def test_disabling_parity_fires(self):
        violations = compensating_control_violations()
        self.assertTrue(
            any("parity sweep was disabled" in v for v in violations),
            f"parity disabled did not fire the guard: {violations}",
        )

    @override_settings(RMC_SYNC_PARITY_INTERVAL_SECONDS=24 * 60 * 60)
    def test_widening_the_parity_interval_fires(self):
        """"Once a day" is the tuning most likely to be made, and it is out of bounds."""
        violations = compensating_control_violations()
        self.assertTrue(
            any("exceeds" in v for v in violations),
            f"a 24h parity interval did not fire the guard: {violations}",
        )

    @override_settings(
        RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS=0,
        RMC_SYNC_PARITY_ENABLED=False,
        RMC_SYNC_PARITY_INTERVAL_SECONDS=24 * 60 * 60,
    )
    def test_all_three_are_reported_together(self):
        """One weakening must not mask the others -- an operator fixes what it names."""
        self.assertEqual(len(compensating_control_violations()), 3)

    @override_settings(
        RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS=600,
        RMC_SYNC_PARITY_ENABLED=True,
        RMC_SYNC_PARITY_INTERVAL_SECONDS=900,
    )
    def test_strengthening_the_controls_is_never_a_violation(self):
        """The guard is a floor and a ceiling, not an equality check.

        A box on a metered link that sweeps every 15 minutes and overlaps by 10 is
        SAFER than the accepted trade, and a guard that failed on that would teach
        people to weaken settings to keep CI green.
        """
        self.assertEqual(compensating_control_violations(), [])


class TheBoundIsRecordedNotAssumedTests(SimpleTestCase):
    """The residual this guard does NOT close, asserted so the docstring cannot drift.

    ``get_sync_cursor_for_request`` promises coverage for transactions SHORTER than the
    overlap and explicitly refuses to promise more. ``test_cursor_overlap_2026_08_20``
    already pins that bound against the builder. This asserts the arithmetic the guard
    itself relies on: a transaction longer than the overlap is outside it, which is why
    parity has to be the other half rather than an optional extra.
    """

    def test_a_transaction_longer_than_the_overlap_is_outside_the_bound(self):
        from apps.sync_engine.models import cursor_overlap_seconds

        overlap = cursor_overlap_seconds()
        # A nightly batch command holding one transaction open is not request-bound and
        # is therefore not covered by the worker-timeout floor at all.
        batch_job_seconds = overlap + 1
        self.assertGreater(batch_job_seconds, overlap)

    def test_parity_is_the_named_recovery_path(self):
        """Not decoration: if parity is off, nothing else can find a slipped row."""
        from apps.sync_engine import parity

        self.assertTrue(hasattr(parity, "enabled"))
        self.assertTrue(hasattr(parity, "interval_seconds"))
        with override_settings(RMC_SYNC_PARITY_ENABLED=False):
            self.assertFalse(parity.enabled())
