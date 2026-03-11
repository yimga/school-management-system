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

from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

# Budgets (p95 response time seconds, max query count) — align with docs/PERFORMANCE_BUDGETS.md
BUDGETS = [
    ("Role home (backend dashboard)", "/authentication/backend/", 1.2, 25, True),
    ("Setup Studio", "/siteconfig/guided-onboarding/", 1.5, 35, True),
    ("Metadata catalog view", "/siteconfig/metadata-catalog/", 1.0, 30, True),
]

STRICT = os.environ.get("PERF_BUDGET_STRICT", "0") == "1"


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
    # Query count is only recorded when DEBUG=True; time is always measured.
    client = get_client_with_user()
    failed = []
    for label, path, max_time, max_queries, _ in BUDGETS:
        start = time.perf_counter()
        with CaptureQueriesContext(connection):
            client.get(path)
        elapsed = time.perf_counter() - start
        num_queries = len(connection.queries)  # 0 if DEBUG=False
        over_time = elapsed > max_time
        over_queries = (num_queries > max_queries) if (max_queries and num_queries > 0) else False
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
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
