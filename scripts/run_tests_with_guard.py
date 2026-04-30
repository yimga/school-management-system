#!/usr/bin/env python3
"""
Run a subprocess with stall and wall-clock timeouts (cross-platform).

  --stall-seconds N   If no output line for N seconds, kill child (default 300).
                      Catches hangs during "Creating test database..." / migrate / stuck tests.
  --max-seconds N     Hard cap on wall time (0 = unlimited).

Example:
  python scripts/run_tests_with_guard.py --stall-seconds 300 --max-seconds 7200 -- \\
    python manage.py test --noinput
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stall-seconds",
        type=float,
        default=float(os.environ.get("RMC_TEST_STALL_SECONDS", "300")),
        help="Kill if no line received for this long (default 300)",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=float(os.environ.get("RMC_TEST_MAX_SECONDS", "0") or 0),
        help="Hard kill after total elapsed seconds (0 = no limit)",
    )
    parser.add_argument(
        "cmd",
        nargs=argparse.REMAINDER,
        help="Command after --",
    )
    args = parser.parse_args()
    cmd = args.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("run_tests_with_guard: missing command after --", file=sys.stderr)
        return 2

    repo = Path(__file__).resolve().parent.parent
    lock = threading.Lock()
    last_line_at = time.monotonic()
    start = time.monotonic()

    def touch() -> None:
        nonlocal last_line_at
        with lock:
            last_line_at = time.monotonic()

    proc = subprocess.Popen(
        cmd,
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
        text=True,
        bufsize=1,
    )
    stop_evt = threading.Event()

    def watchdog() -> None:
        while not stop_evt.wait(2.0):
            if proc.poll() is not None:
                return
            with lock:
                idle = time.monotonic() - last_line_at
            if idle > args.stall_seconds:
                print(
                    f"\n[run_tests_with_guard] FAIL: no output for {idle:.0f}s "
                    f"(>{args.stall_seconds}s stall threshold)\n",
                    file=sys.stderr,
                )
                proc.kill()
                return
            if args.max_seconds > 0 and (time.monotonic() - start) > args.max_seconds:
                print(
                    f"\n[run_tests_with_guard] FAIL: exceeded --max-seconds {args.max_seconds}\n",
                    file=sys.stderr,
                )
                proc.kill()
                return

    wd = threading.Thread(target=watchdog, daemon=True)
    wd.start()

    assert proc.stdout is not None
    rc: int | None = None
    try:
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            touch()
        rc = proc.wait(timeout=30)
    except Exception:
        proc.kill()
        raise
    finally:
        stop_evt.set()

    return int(rc) if rc is not None else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
