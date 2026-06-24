#!/usr/bin/env python3
"""
Operator smoke — live Prometheus compose stack + app /metrics/ scrape path.

Checks (best-effort, no Django required for HTTP probes):
  1. deploy/observability/docker-compose.yml parses (`docker compose config`)
  2. Prometheus health: GET http://localhost:9090/-/healthy
  3. App metrics: GET $RMC_METRICS_URL (default http://127.0.0.1:10000/metrics/)
     — 200 + body contains runmycampus_ when OBSERVABILITY_METRICS_BACKEND=prometheus-client

Default exit 0 when the stack is not running (operator laptop / CI without compose).
Use --strict to fail when Prometheus or /metrics/ is unreachable.

Usage:
  python scripts/verify_prometheus_stack_live.py
  python scripts/verify_prometheus_stack_live.py --strict
  RMC_METRICS_URL=http://host.docker.internal:8000/metrics/ python scripts/verify_prometheus_stack_live.py --strict

See docs/PROMETHEUS_OPERATOR_DEPLOY_RUNBOOK.md
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "deploy/observability/docker-compose.yml"
DEFAULT_METRICS_URL = os.environ.get("RMC_METRICS_URL", "http://127.0.0.1:10000/metrics/")
DEFAULT_PROM_URL = os.environ.get("RMC_PROMETHEUS_URL", "http://127.0.0.1:9090/-/healthy")
PROBE_TIMEOUT = float(os.environ.get("RMC_PROMETHEUS_PROBE_TIMEOUT", "4"))


def _http_get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as resp:
            body = resp.read(65536).decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read(65536).decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, ""


def _compose_config_ok() -> tuple[bool, str]:
    if not COMPOSE.is_file():
        return False, f"missing {COMPOSE.relative_to(ROOT)}"
    docker = shutil.which("docker")
    if not docker:
        return True, "docker not installed — skipped compose config parse"
    try:
        proc = subprocess.run(
            [docker, "compose", "-f", str(COMPOSE), "config"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"docker compose config failed: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, detail[-1] if detail else "docker compose config non-zero exit"
    return True, "docker compose config OK"


def _django_backend() -> str:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        import django

        django.setup()
        from django.conf import settings

        return str(getattr(settings, "OBSERVABILITY_METRICS_BACKEND", "noop"))
    except Exception:  # noqa: BLE001 — operator script; HTTP probe still runs
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Live Prometheus stack + /metrics/ smoke.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when Prometheus or /metrics/ is unreachable.",
    )
    parser.add_argument(
        "--skip-compose",
        action="store_true",
        help="Skip docker compose config parse.",
    )
    args = parser.parse_args()

    findings: list[str] = []
    notes: list[str] = []

    if not args.skip_compose:
        ok, msg = _compose_config_ok()
        print(f"  compose: {msg}")
        if not ok:
            findings.append(msg)

    prom_status, prom_body = _http_get(DEFAULT_PROM_URL)
    prom_up = prom_status == 200 and "Prometheus" in prom_body
    print(f"  prometheus ({DEFAULT_PROM_URL}): status={prom_status or 'unreachable'} up={prom_up}")

    metrics_status, metrics_body = _http_get(DEFAULT_METRICS_URL)
    metrics_has_series = "runmycampus_" in metrics_body
    metrics_ok = metrics_status == 200 and metrics_has_series
    print(
        f"  metrics ({DEFAULT_METRICS_URL}): status={metrics_status or 'unreachable'} "
        f"runmycampus_series={metrics_has_series}"
    )

    backend = _django_backend()
    print(f"  OBSERVABILITY_METRICS_BACKEND={backend!r}")

    if backend != "prometheus-client" and metrics_status == 404:
        notes.append(
            "/metrics/ returned 404 — set OBSERVABILITY_METRICS_BACKEND=prometheus-client "
            "and pip install prometheus_client before expecting scrape data."
        )
    elif backend == "prometheus-client" and not metrics_ok:
        findings.append(
            "Backend is prometheus-client but /metrics/ did not return runmycampus_ series."
        )

    if not prom_up:
        findings.append(
            f"Prometheus not healthy at {DEFAULT_PROM_URL} — "
            "run: docker compose -f deploy/observability/docker-compose.yml up -d"
        )

    if findings:
        print("\nFindings:")
        for msg in findings:
            print(f"  - {msg}")
        for msg in notes:
            print(f"  note: {msg}")
        if args.strict:
            print("\nPROMETHEUS_STACK_LIVE_FAIL")
            return 1
        print(
            "\nStack not fully live — soft pass (re-run with --strict after "
            "compose up + app on prometheus-client backend)."
        )
        print("PROMETHEUS_STACK_LIVE_SOFT_PASS")
        return 0

    for msg in notes:
        print(f"  note: {msg}")
    print("\nPROMETHEUS_STACK_LIVE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
