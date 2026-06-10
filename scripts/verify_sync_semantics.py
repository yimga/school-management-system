#!/usr/bin/env python3
"""Phase P5 gate for governed local-first synchronization semantics."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
