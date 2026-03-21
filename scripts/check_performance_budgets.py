#!/usr/bin/env python3
"""
Path-to-10: Performance budget check (docs/PERFORMANCE_BUDGETS.md).
Runs a small set of smoke requests and fails if any budget is exceeded.
Set PERF_BUDGET_STRICT=1 to fail on exceed; otherwise warns and exits 0.
"""

from __future__ import annotations

import os
import sys
import time

# Django setup
if os.environ.get("DJANGO_SETTINGS_MODULE") is None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import django

django.setup()

from django.core.exceptions import DisallowedHost
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.db import connection

# label, path, max_time_s, max_queries, enforce_when_strict_only_if_false_skip
# anonymous=True: unauthenticated client (public marketing, etc.)
BUDGETS = [
    {
        "label": "Role home (backend dashboard)",
        "path": "/authentication/backend/",
        "max_time": 1.2,
        "max_queries": 25,
        "enforce": True,
        "anonymous": False,
    },
    {
        "label": "Setup Studio",
        "path": "/siteconfig/guided-onboarding/",
        "max_time": 1.5,
        "max_queries": 35,
        "enforce": True,
        "anonymous": False,
    },
    {
        "label": "Metadata catalog view",
        "path": "/siteconfig/metadata-catalog/",
        "max_time": 1.0,
        "max_queries": 30,
        "enforce": True,
        "anonymous": False,
    },
    {
        "label": "Super advancement hub",
        "path": "/super/advancement/",
        "max_time": 1.0,
        "max_queries": 20,
        "enforce": False,
        "anonymous": False,
    },
    {
        "label": "Super geography",
        "path": "/super/geography/",
        "max_time": 1.0,
        "max_queries": 25,
        "enforce": False,
        "anonymous": False,
    },
    {
        "label": "Tenant advancement donors list",
        "path": "/authentication/backend/advancement/donors/",
        "max_time": 1.0,
        "max_queries": 20,
        "enforce": True,
        "anonymous": False,
    },
    {
        "label": "Marketing landing (public, N10 proxy)",
        "path": "/marketing/",
        "max_time": 3.5,
        "max_queries": 220,
        "enforce": True,
        "anonymous": True,
        "n10_ci_only": True,
    },
]

# When PERF_BUDGET_STRICT_GATE_ROWS=n10_public, only rows with n10_ci_only run
# (stable CI for N10 without failing on staff paths' query volume under DEBUG).
_N10_CI = os.environ.get("PERF_BUDGET_STRICT_GATE_ROWS", "").strip().lower() == "n10_public"

STRICT = os.environ.get("PERF_BUDGET_STRICT", "0") == "1"
N10_STRICT = os.environ.get("PERF_BUDGET_STRICT_N10", "0") == "1"
N10_TIME_FACTOR = 0.75 if N10_STRICT else 1.0
_HTTP_HOST = (os.environ.get("PERF_BUDGET_HTTP_HOST") or "127.0.0.1").strip()


def _get(client, path: str):
    try:
        return client.get(path, HTTP_HOST=_HTTP_HOST)
    except DisallowedHost:
        return client.get(path)


def get_client_with_user():
    """Return a test client logged in as staff so protected URLs respond 200."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    client = Client()
    user = User.objects.filter(is_staff=True).first()
    if user:
        client.force_login(user)
    return client


def run_budget_check():
    budget_list = (
        [b for b in BUDGETS if b.get("n10_ci_only")]
        if _N10_CI
        else list(BUDGETS)
    )
    client_staff = get_client_with_user()
    client_anon = Client()
    failed = []
    for row in budget_list:
        label = row["label"]
        path = row["path"]
        max_time = max(0.05, float(row["max_time"]) * N10_TIME_FACTOR)
        max_queries = int(row["max_queries"])
        client = client_anon if row.get("anonymous") else client_staff
        start = time.perf_counter()
        with CaptureQueriesContext(connection):
            _get(client, path)
        elapsed = time.perf_counter() - start
        num_queries = len(connection.queries)
        over_time = elapsed > max_time
        over_queries = (
            (num_queries > max_queries) if (max_queries and num_queries > 0) else False
        )
        if over_time or over_queries:
            msg = f"{label}: time={elapsed:.2f}s (budget {max_time}s), queries={num_queries} (budget {max_queries})"
            failed.append((label, msg, over_time, over_queries))
            print(f"BUDGET EXCEEDED: {msg}", file=sys.stderr)
        else:
            print(f"OK: {label} {elapsed:.2f}s, {num_queries} queries")
    return failed


def main():
    failed = run_budget_check()
    if failed and STRICT:
        print("Set PERF_BUDGET_STRICT=0 to warn only.", file=sys.stderr)
        if N10_STRICT:
            print(
                "PERF_BUDGET_STRICT_N10=1 applied tighter time budgets (N10 partial).",
                file=sys.stderr,
            )
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
