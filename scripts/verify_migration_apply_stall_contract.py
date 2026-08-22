#!/usr/bin/env python3
"""Seal migration apply stall detection: row pulses must feed LoopWatchdog."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    failures: list[str] = []

    loop_wd = (ROOT / "apps" / "migration_cloud" / "loop_watchdog.py").read_text(
        encoding="utf-8"
    )
    if "rows_processed" not in loop_wd:
        failures.append("loop_watchdog.py must track rows_processed as progress")
    if "threading.Lock" not in loop_wd:
        failures.append("loop_watchdog.py must be thread-safe for parallel apply")

    unified = (ROOT / "apps" / "migration_cloud" / "unified_progress.py").read_text(
        encoding="utf-8"
    )
    if "on_stall_heartbeat" not in unified or "_maybe_stall_heartbeat" not in unified:
        failures.append(
            "unified_progress.py must pulse stall heartbeats from register_row"
        )

    orch = (ROOT / "apps" / "migration_cloud" / "orchestrator.py").read_text(encoding="utf-8")
    required_orchestrator = (
        "LoopWatchdog",
        "on_stall_heartbeat",
        "rows_processed=apply_tracker.rows_global",
        "_stall_watchdog_heartbeat",
        "SystemicStallError",
        "systemic_stall",
        "resolve_stall_timeout_seconds",
        "set_stall_pulse_hook",
    )
    for token in required_orchestrator:
        if token not in orch:
            failures.append(f"orchestrator.py missing stall contract token: {token}")
    if "timeout_seconds=120" in orch or "timeout_seconds=120.0" in orch:
        failures.append(
            "orchestrator.py must not hardcode 120s stall timeout — use resolve_stall_timeout_seconds"
        )

    defaults = (ROOT / "apps" / "migration_cloud" / "defaults.py").read_text(encoding="utf-8")
    for key in (
        "migration_cloud.apply.stall_timeout_seconds",
        "migration_cloud.apply.stall_timeout_row_scale_per_1000",
        "migration_cloud.apply.stall_timeout_min_seconds",
        "migration_cloud.apply.stall_timeout_max_seconds",
        "migration_cloud.repair.applying_stale_seconds",
        "migration_cloud.repair.applying_stale_row_scale_per_1000",
        "migration_cloud.repair.applying_stale_min_seconds",
        "migration_cloud.repair.applying_stale_max_seconds",
    ):
        if key not in defaults:
            failures.append(f"defaults.py missing stall config key: {key}")

    apply_stall = ROOT / "apps" / "migration_cloud" / "apply_stall.py"
    if not apply_stall.is_file():
        failures.append("apply_stall.py must exist")
    else:
        apply_stall_src = apply_stall.read_text(encoding="utf-8")
        for token in (
            "resolve_stall_timeout_seconds",
            "resolve_applying_stale_seconds",
            "maybe_stall_pulse",
            "read_with_stall_pulse",
            "set_stall_pulse_hook",
            "stall_pulse_scope",
        ):
            if token not in apply_stall_src:
                failures.append(f"apply_stall.py missing: {token}")

    streaming_gate = ROOT / "scripts" / "scan_lander_row_streaming.py"
    if not streaming_gate.is_file():
        failures.append("scripts/scan_lander_row_streaming.py must exist")
    else:
        import subprocess

        proc = subprocess.run(
            [sys.executable, str(streaming_gate), "--strict"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            failures.append(
                "scan_lander_row_streaming.py --strict failed — landers buffer without allow"
            )

    helpers = (ROOT / "apps" / "migration_cloud" / "landers" / "_helpers.py").read_text(
        encoding="utf-8"
    )
    if "def maybe_stall_pulse" not in helpers:
        failures.append("_helpers.py must re-export maybe_stall_pulse for landers")

    repair = (ROOT / "apps" / "migration_cloud" / "repair.py").read_text(encoding="utf-8")
    if "MigrationProgressEvent" not in repair or "applying_stale_by_time" not in repair:
        failures.append(
            "repair.py must measure wedged apply from progress events, not viewer saves"
        )
    if "resolve_applying_stale_seconds" not in repair:
        failures.append("repair.py must use tier-scaled applying_stale threshold")

    orch_parse_tokens = ("read_with_stall_pulse", "maybe_stall_pulse()")
    if not all(token in orch for token in orch_parse_tokens):
        failures.append(
            "orchestrator.py must pulse during artifact parse (read_with_stall_pulse / maybe_stall_pulse)"
        )

    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        print(f"verify_migration_apply_stall_contract: {len(failures)} FAIL", file=sys.stderr)
        return 1
    print("verify_migration_apply_stall_contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
