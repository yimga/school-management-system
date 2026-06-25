#!/usr/bin/env python3
"""
Measure platform surface + context-processor hot-path cost (stdlib-only driver).

Usage (from repo root):
  DB_LOG_LEVEL=WARNING python scripts/bench_platform_surface_hotpath.py

Prints reverse() call counts and wall time for the pre-fix triple-resolve pattern
vs the request-scoped cache path.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DB_LOG_LEVEL", "WARNING")

import django

django.setup()

from django.test import RequestFactory

from apps.siteconfig.context_processors import platform_surface_settings
from apps.siteconfig.platform_surface_config import (
    platform_surface_config_json,
    resolve_platform_surface_config,
    resolve_sms_offline_config,
)


def _bench(label: str, fn) -> tuple[float, int]:
    reverse_calls = 0
    original = __import__(
        "apps.siteconfig.platform_surface_config", fromlist=["reverse"]
    ).reverse

    def counting_reverse(name, *args, **kwargs):
        nonlocal reverse_calls
        reverse_calls += 1
        return original(name, *args, **kwargs)

    with mock.patch(
        "apps.siteconfig.platform_surface_config.reverse", side_effect=counting_reverse
    ):
        t0 = time.perf_counter()
        fn()
        elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"{label}: reverse_calls={reverse_calls} elapsed_ms={elapsed_ms:.2f}")
    return elapsed_ms, reverse_calls


def main() -> int:
    rf = RequestFactory()
    req = rf.get("/portal/parent/dashboard/")

    def simulate_old_triple_resolve():
        resolve_platform_surface_config(req)
        platform_surface_config_json(req)
        resolve_sms_offline_config(req, offline_enabled_for_school=False)

    def simulate_context_processor():
        platform_surface_settings(req)

    # Warm Django URL resolver once (excluded from timed sections below).
    from django.urls import reverse

    try:
        reverse("portal:home")
    except Exception:
        pass

    print("--- platform surface hot path (same request) ---")
    req2 = rf.get("/portal/parent/dashboard/")
    _bench("triple_call_pattern", simulate_old_triple_resolve)

    req3 = rf.get("/portal/parent/dashboard/")
    _bench("context_processor_platform_surface_settings", simulate_context_processor)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
