"""
Operator read-only view: summarizes generated security_surface_audit.json.

Run ``python scripts/audit_security_surface.py`` before relying on freshness.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET


def _repo_root() -> Path:
    return Path(settings.BASE_DIR).resolve()


def _load_security_audit() -> dict:
    path = _repo_root() / "docs" / "generated" / "security_surface_audit.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def _load_post_handler_audit() -> dict:
    path = _repo_root() / "docs" / "generated" / "post_handler_audit.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def _load_post_surface_audit() -> dict:
    """Combined POST / CSRF / AllowAny / raw-SQL / subprocess / export hints ledger."""
    path = _repo_root() / "docs" / "generated" / "post_surface_audit.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def _review_rows(payload: dict, *, limit: int = 120) -> list[dict]:
    unified = payload.get("unified") or []
    if not isinstance(unified, list):
        return []
    need = []
    for row in unified:
        if not isinstance(row, dict):
            continue
        tier = str(row.get("governance_tier") or "")
        cls = str(row.get("classification") or "")
        if tier in ("needs_review", "violation") or cls in ("needs_review", "unsafe"):
            need.append(row)
        if len(need) >= limit:
            break
    return need


@require_GET
def super_security_surface_dashboard(request):
    """Super-admin: governance summary + first review rows from generated JSON."""
    payload = _load_security_audit()
    post_audit = _load_post_handler_audit()
    post_surface_audit = _load_post_surface_audit()
    summary_by_tier = payload.get("summary_by_governance_tier") or {}
    summary_by_classification = payload.get("summary_by_classification") or {}
    counts = payload.get("summary") or {}
    totals = payload.get("totals") or {}
    review_rows = _review_rows(payload)
    summary_signals = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    post_surface_summary: dict = {}
    post_surface_missing = not bool(post_surface_audit)
    if isinstance(post_surface_audit, dict):
        raw_sum = post_surface_audit.get("summary")
        post_surface_summary = raw_sum if isinstance(raw_sum, dict) else {}
    # Strip card: use security_surface counts; fill gaps from post_surface ledger / embed.
    merged_signals = dict(summary_signals)
    if isinstance(post_surface_audit, dict):
        emb = post_surface_audit.get("security_surface_audit_embed") or {}
        emb_sum = emb.get("summary") if isinstance(emb.get("summary"), dict) else {}
        for k, v in emb_sum.items():
            merged_signals.setdefault(k, v)
        ps = post_surface_summary
        if not merged_signals.get("csrf_exempt") and ps.get("csrf_exempt_hits_apps") is not None:
            merged_signals["csrf_exempt"] = ps["csrf_exempt_hits_apps"]
        if not merged_signals.get("allow_any") and ps.get("allow_any_hint_hits") is not None:
            merged_signals["allow_any"] = ps["allow_any_hint_hits"]
        if not merged_signals.get("cursor_execute") and ps.get("cursor_execute_hits_apps") is not None:
            merged_signals["cursor_execute"] = ps["cursor_execute_hits_apps"]
        if not merged_signals.get("subprocess") and ps.get("subprocess_hits_apps") is not None:
            merged_signals["subprocess"] = ps["subprocess_hits_apps"]
    post_totals = {}
    if isinstance(post_audit, dict):
        post_totals = post_audit.get("totals") if isinstance(post_audit.get("totals"), dict) else {}
    return render(
        request,
        "schools/super_security_surface_dashboard.html",
        {
            "page_title": "Security surface (generated audit)",
            "dashboard_url": reverse("super:dashboard"),
            "generated_at": payload.get("generated_at"),
            "summary_by_tier": summary_by_tier,
            "summary_by_classification": summary_by_classification,
            "pattern_counts": counts,
            "totals": totals,
            "review_rows": review_rows,
            "audit_missing": not bool(payload),
            "post_handler_audit": post_audit,
            "post_audit_missing": not bool(post_audit),
            "post_surface_audit": post_surface_audit,
            "post_surface_summary": post_surface_summary,
            "post_surface_missing": post_surface_missing,
            "support_visibility_url": reverse("super:support_dashboard"),
            "security_signal_summary": merged_signals,
            "post_audit_totals": post_totals,
        },
    )
