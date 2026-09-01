#!/usr/bin/env python3
"""Phase P5 gate for governed local-first synchronization semantics.

Also the home of the G8 compensating-control check (see
:func:`compensating_control_violations`). It was promoted here from
``apps/sync_engine/tests/test_accepted_risk_compensating_controls_2026_08_31.py``
on 2026-09-01: the bounds it asserts are properties of a DEPLOYMENT's settings,
not of the code, so a check that only ever ran inside the test suite answered the
question for the CI settings and for nothing else. A gate an operator can point at
a real environment is the only version of it that is worth anything. The test still
drives the same function -- it imports it from here -- so there is one definition,
not two that can drift.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

#: A school day is ~8h; twice a day means a morning slip is found before the day ends.
PARITY_INTERVAL_CEILING_SECONDS = 6 * 60 * 60  # magic-number-allow: 6h parity sweep ceiling


def _ensure_django() -> None:
    """Set Django up if nobody has. A no-op under ``manage.py test``.

    Deliberately lazy rather than module-level: this module is loaded by
    ``apps.sync_engine.tests.test_accepted_risk_compensating_controls_2026_08_31``
    inside an already-configured test process, and importing it must have no side
    effects there.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.apps import apps as django_apps

    if not django_apps.ready:
        import django

        django.setup()


def cursor_overlap_floor_seconds() -> int:
    """The longest transaction a web request can hold open on this deployment.

    Derived, not declared: it is the gunicorn worker timeout, because the worker is
    killed at it. Reading the real plan rather than hard-coding 120 means an operator
    who RAISES ``GUNICORN_TIMEOUT`` also raises this floor, which is the correct
    direction -- a longer permitted request is a longer window to cover.
    """
    try:
        from services.web_runtime import plan_web_runtime

        return int(plan_web_runtime(os.environ).timeout)
    except Exception:  # noqa: BLE001 - a guard that cannot read the plan still guards
        # The static fallback gunicorn itself uses when sizing is unavailable.
        return 120


def compensating_control_violations() -> list[str]:
    """Every way the G8 trade is currently weaker than it was accepted at.

    WHAT WAS ACCEPTED. ``sync_engine.models.get_sync_cursor_for_request`` states its own
    limit plainly: the rail is not a transactional outbox, so a transaction that stays
    open LONGER than the cursor overlap can commit an ``updated_at`` already behind the
    recorded high-water and never be offered again. The trade is right for ONE reason,
    and that reason is a compensating control, not the overlap itself:

        the overlap makes a slip UNLIKELY;
        the parity sweep (``apps.sync_engine.parity``) makes a slip FINDABLE.

    Both halves are ordinary settings, so either can be tuned away by someone debugging
    a slow box -- and nothing else in the engine would notice, because an incremental
    delta only offers what changed SINCE the cursor and a slipped row has no
    ``updated_at`` greater than anything.

    Returns a list of sentences, empty when the trade still holds. A list rather than a
    raise so callers (this gate, and the test that drives it under a deliberately
    weakened setting) can SEE it fire -- a guard nobody has watched fail is not a guard.
    """
    _ensure_django()
    from apps.sync_engine import parity
    from apps.sync_engine.models import cursor_overlap_seconds

    violations: list[str] = []

    floor = cursor_overlap_floor_seconds()
    overlap = cursor_overlap_seconds()
    if overlap < floor:
        violations.append(
            f"protected cursor overlap was weakened: "
            f"RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS={overlap} is below the "
            f"{floor}s gunicorn worker timeout, so a request-bound transaction can "
            f"commit behind the cursor and never be re-offered"
        )

    if not parity.enabled():
        violations.append(
            "protected parity sweep was disabled: RMC_SYNC_PARITY_ENABLED is off, so a "
            "row that slipped past the cursor can never be found again -- an "
            "incremental delta only offers what changed SINCE the cursor"
        )

    interval = parity.interval_seconds()
    if interval > PARITY_INTERVAL_CEILING_SECONDS:
        violations.append(
            f"protected parity sweep was weakened: "
            f"RMC_SYNC_PARITY_INTERVAL_SECONDS={interval} exceeds the "
            f"{PARITY_INTERVAL_CEILING_SECONDS}s ceiling, so a row that slips in the "
            f"morning is not looked for before the school day ends"
        )

    return violations


def main() -> int:
    errors: list[str] = []
    registry = (ROOT / "apps" / "sync_engine" / "policy_registry.py").read_text(
        encoding="utf-8"
    )
    resolver = (ROOT / "apps" / "sync_engine" / "conflict_resolver.py").read_text(
        encoding="utf-8"
    )
    protocol = (
        ROOT / "apps" / "sync_engine" / "crdt_wire_protocol.py"
    ).read_text(encoding="utf-8")
    view = (ROOT / "apps" / "sync_engine" / "views_crdt.py").read_text(
        encoding="utf-8"
    )
    client = (ROOT / "static" / "js" / "rmc-crdt-client.js").read_text(
        encoding="utf-8"
    )
    offline_client = (
        ROOT / "static" / "js" / "offline-queue-client.js"
    ).read_text(encoding="utf-8")

    for token in (
        "POLICY_VERSION",
        '"grade_entry"',
        '"fee_payment"',
        '"permission_grant"',
        "protected=True",
        "validate_crdt_kind",
    ):
        if token not in registry:
            errors.append(f"sync policy registry missing: {token}")
    for token in (
        "override_blocked",
        "remote_clock",
        "server_clock",
        "causal_lww requires",
    ):
        if token not in resolver:
            errors.append(f"conflict resolver contract missing: {token}")
    for token in (
        "__removed__:",
        "absolute value",
        "max(new_state.get(op.actor_id, 0), op.value)",
    ):
        if token not in protocol:
            errors.append(f"CRDT convergence contract missing: {token}")
    for token in (
        "select_for_update",
        "_bound_actor_id",
        "_validate_key_namespace",
        "policy_version",
    ):
        if token not in view:
            errors.append(f"governed CRDT endpoint missing: {token}")
    for token in (
        "Math.trunc(Number(physicalMs)",
        "this._counterCells",
        "value: nextValue",
        "device_id: this.deviceId",
    ):
        if token not in client:
            errors.append(f"CRDT browser client contract missing: {token}")
    for token in (
        "CAUSAL_COUNTER_KEY",
        "CAUSAL_REPLICA_KEY",
        "nextCausalClock",
        "causal_clock:",
    ):
        if token not in offline_client:
            errors.append(f"offline causal envelope missing: {token}")

    # G8: the accepted risk stays accepted, or this gate fails. Run against the
    # settings this process actually has, which is the point of running it here rather
    # than only inside the test suite. A check that cannot be READ is reported as a
    # failure, not skipped -- a gate that quietly passes when it cannot look is worse
    # than no gate.
    try:
        errors.extend(compensating_control_violations())
    except Exception as exc:  # noqa: BLE001 - a gate that cannot run has FAILED
        errors.append(
            f"compensating-control check could not run: {type(exc).__name__}: {exc}"
        )

    commands = [
        [
            sys.executable,
            "scripts/run_sqlite_memory_tests.py",
            "apps.sync_engine.tests.test_sync_policy_registry",
            "apps.sync_engine.tests.test_conflict_resolver",
            "apps.sync_engine.tests.test_crdt",
            "apps.sync_engine.tests.test_crdt_wire_protocol",
            "apps.sync_engine.tests.test_crdt_view_governance",
            "apps.sync_engine.tests.test_delta_bundle",
            "apps.sync_engine.tests.test_event_envelope",
            "apps.sync_engine.tests.test_services",
            "apps.sync_engine.tests.test_sodp_conflict_grade",
            "apps.platform_runtime.tests.test_offline_grading_manual_review",
            "apps.platform_runtime.tests.test_offline_queue.OfflineQueueHelpersTests",
            "--verbosity=1",
        ],
        [sys.executable, "manage.py", "verify_sync_semantics"],
        [sys.executable, "manage.py", "check"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            errors.append(f"verification command failed: {' '.join(command)}")

    if errors:
        print("LOCAL_FIRST_SYNC_CONTRACT_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("LOCAL_FIRST_SYNC_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
