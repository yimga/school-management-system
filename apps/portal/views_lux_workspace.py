"""Demo view for the lux-workspace luxury UI surface.

Mounts the React orchestrator + Cmd+K console + tier-personality canvases
under /portal/lux-workspace/?tier=FINANCIAL_LEDGER (or ACADEMIC_MATRIX /
OPERATOR_SHELL).  Reads the localized labels via lux_workspace_i18n so the
React layer can swap in tenant-locale strings on mount.
"""

from __future__ import annotations

import json

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .lux_workspace_i18n import render_lux_i18n_script

_DEMO_STUDENTS = [
    {"id": "s-1001", "firstName": "John", "lastName": "Doe",
     "cycleLabel": "Form 5 · Science", "ledgerStatus": "PAID",
     "performanceMark": "89%"},
    {"id": "s-1002", "firstName": "Adaora", "lastName": "Okafor",
     "cycleLabel": "Form 5 · Science", "ledgerStatus": "PAID",
     "performanceMark": "92%"},
    {"id": "s-1003", "firstName": "Bola", "lastName": "Kareem",
     "cycleLabel": "Form 5 · Science", "ledgerStatus": "OVERDUE",
     "performanceMark": "65%"},
    {"id": "s-1004", "firstName": "Chinedu", "lastName": "Eze",
     "cycleLabel": "Form 4 · Arts", "ledgerStatus": "PENDING",
     "performanceMark": "78%"},
    {"id": "s-1005", "firstName": "Dami", "lastName": "Adeyemi",
     "cycleLabel": "Form 4 · Arts", "ledgerStatus": "PAID",
     "performanceMark": "77%"},
]

_VALID_TIERS = {"FINANCIAL_LEDGER", "ACADEMIC_MATRIX", "OPERATOR_SHELL"}


def lux_workspace_demo(request: HttpRequest) -> HttpResponse:
    initial_tier = (request.GET.get("tier") or "FINANCIAL_LEDGER").upper()
    if initial_tier not in _VALID_TIERS:
        initial_tier = "FINANCIAL_LEDGER"
    try:
        simulate_async_ms = int(request.GET.get("simulate_async_ms") or 0)
    except (TypeError, ValueError):
        simulate_async_ms = 0
    simulate_async_ms = max(0, min(simulate_async_ms, 30_000))  # magic-number-allow: millisecond-timeout
    return render(
        request,
        "lux_workspace/demo.html",
        {
            "initial_tier": initial_tier,
            "student_seeds_json": json.dumps(_DEMO_STUDENTS),
            "simulate_async_ms": simulate_async_ms,
            "lux_i18n_json": render_lux_i18n_script(),
        },
    )
