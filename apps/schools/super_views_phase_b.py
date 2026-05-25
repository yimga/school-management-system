"""
Phase B operator surfaces: live slim tenant settings row vs materialized domain snapshots (diff).
"""

from __future__ import annotations

import difflib
import hashlib
import json
from typing import Any

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_SECURITY_READ,
    require_platform_scope,
)
from apps.platform_runtime.models import (
    PlatformOperatorPhaseBLink,
    PlatformPhaseBDomainSnapshot,
)
from apps.platform_runtime.phase_b_operator_labels import phase_b_operator_card_text
from apps.platform_runtime.phase_b_domain_snapshots import (
    PHASE_B_SNAPSHOT_DOMAINS,
    diff_top_level_payload_keys,
    phase_b_payload_metadata,
    snapshot_payload_for_domain,
    sync_phase_b_domain_snapshots_from_site,
)

from .decision_architecture import get_decision_architecture_for_page


def _phase_b_domain_detail_bundle(
    site, focus_domain: str
) -> tuple[dict[str, Any], str]:
    """Key-level diff metadata + unified diff text for one Phase B snapshot domain."""
    live = snapshot_payload_for_domain(site, focus_domain) if site else {}
    row = PlatformPhaseBDomainSnapshot.objects.filter(pk=focus_domain).first()
    stored = row.payload if row and isinstance(row.payload, dict) else {}
    key_detail = diff_top_level_payload_keys(live, stored)
    snap_lines = json.dumps(stored, indent=2, sort_keys=True, default=str).splitlines()
    live_lines = json.dumps(live, indent=2, sort_keys=True, default=str).splitlines()
    diff_text = "\n".join(
        difflib.unified_diff(
            snap_lines,
            live_lines,
            fromfile="snapshot_row",
            tofile="live_owned_payload",
            lineterm="",
        )
    )
    return key_detail, diff_text


def _build_phase_b_domain_rows(site) -> list[dict[str, Any]]:
    """Summary rows for snapshot vs live comparison (HTML table and JSON export)."""
    rows_out: list[dict[str, Any]] = []
    for domain in PHASE_B_SNAPSHOT_DOMAINS:
        live = snapshot_payload_for_domain(site, domain) if site else {}
        live_k, live_h = phase_b_payload_metadata(live)
        row = PlatformPhaseBDomainSnapshot.objects.filter(pk=domain).first()
        stored = row.payload if row and isinstance(row.payload, dict) else {}
        stored_k = getattr(row, "payload_key_count", 0) if row else 0
        stored_h = (getattr(row, "payload_checksum", "") or "").strip() if row else ""
        if not stored_h and row:
            stored_k, stored_h = phase_b_payload_metadata(stored)
        in_sync = bool(row) and live_h == stored_h
        key_diff = diff_top_level_payload_keys(live, stored)
        op_title, op_summary = phase_b_operator_card_text(domain)
        rows_out.append(
            {
                "domain": domain,
                "operator_title": op_title,
                "operator_summary": op_summary,
                "in_sync": in_sync,
                "live_key_count": live_k,
                "stored_key_count": stored_k,
                "live_checksum": live_h,
                "stored_checksum": stored_h,
                "row_updated_at": getattr(row, "updated_at", None),
                "changed_key_count": key_diff["changed_key_count"],
            }
        )
    return rows_out


@require_platform_scope(PLATFORM_SCOPE_SECURITY_READ)
def super_phase_b_snapshot_diff(request):
    """
    Compare live ``owned_payload(domain)`` to persisted ``PlatformPhaseBDomainSnapshot``.

    Drift indicates admin edits without re-save of the slim tenant settings row, failed sync, or manual DB mutation.
    """
    site = get_platform_site_settings_record(create=True)
    focus_domain = (
        request.GET.get("domain") or request.POST.get("focus_domain") or ""
    ).strip()

    if request.method == "POST" and request.POST.get("action") == "resync_all_snapshots":
        if site is not None:
            sync_phase_b_domain_snapshots_from_site(site)
            messages.success(
                request,
                _(
                    "Re-materialized all Phase B domain snapshots from the live slim tenant settings row."
                ),
            )
        else:
            messages.warning(
                request, _("No platform tenant settings row; nothing to sync.")
            )
        dest = reverse("super:phase_b_snapshot_diff")
        if focus_domain:
            dest = f"{dest}?domain={focus_domain}"
        return redirect(dest)

    rows_out = _build_phase_b_domain_rows(site)

    if request.method == "GET" and (request.GET.get("export") or "").strip().lower() == "json":
        domains_json: list[dict[str, Any]] = []
        for r in rows_out:
            ru = r.get("row_updated_at")
            domains_json.append(
                {
                    "domain": r["domain"],
                    "operator_title": r["operator_title"],
                    "operator_summary": r["operator_summary"],
                    "in_sync": r["in_sync"],
                    "changed_key_count": r["changed_key_count"],
                    "live_key_count": r["live_key_count"],
                    "stored_key_count": r["stored_key_count"],
                    "live_checksum": r["live_checksum"],
                    "stored_checksum": r["stored_checksum"],
                    "row_updated_at": ru.isoformat() if ru else None,
                }
            )
        agg_src = "|".join(
            str(r.get("stored_checksum") or "")
            for r in sorted(rows_out, key=lambda x: x["domain"])
        )
        payload: dict[str, Any] = {
            "export_version": 1,
            "generated_at": timezone.now().isoformat(),
            "drift_count": sum(1 for r in rows_out if not r["in_sync"]),
            "aggregate_checksum": hashlib.sha256(agg_src.encode()).hexdigest(),
            "domains": domains_json,
        }
        domain_filter = (request.GET.get("domain") or "").strip()
        if domain_filter in PHASE_B_SNAPSHOT_DOMAINS:
            key_detail, unified_diff = _phase_b_domain_detail_bundle(site, domain_filter)
            payload["export_version"] = 2
            payload["detail_domain"] = domain_filter
            payload["key_detail"] = key_detail
            payload["unified_diff"] = unified_diff
        return JsonResponse(payload)

    diff_text = ""
    detail_domain = ""
    key_detail: dict[str, Any] | None = None
    snapshot_admin_list = reverse(
        "admin:platform_runtime_platformphasebdomainsnapshot_changelist"
    )

    if focus_domain and focus_domain in PHASE_B_SNAPSHOT_DOMAINS:
        detail_domain = focus_domain
        key_detail, diff_text = _phase_b_domain_detail_bundle(site, focus_domain)

    return render(
        request,
        "schools/super_phase_b_snapshot_diff.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "runtime_truth_hub_url": reverse("super:runtime_truth_hub"),
            "snapshot_admin_list": snapshot_admin_list,
            "phase_b_snapshot_diff_url": reverse("super:phase_b_snapshot_diff"),
            "domain_rows": rows_out,
            "drift_count": sum(1 for r in rows_out if not r["in_sync"]),
            "focus_domain": focus_domain,
            "detail_domain": detail_domain,
            "diff_text": diff_text,
            "key_detail": key_detail,
            "operator_phase_b_links": PlatformOperatorPhaseBLink.objects.order_by(
                "sort_order", "slug"
            ),
            "decision_architecture": get_decision_architecture_for_page(
                "phase_b_snapshot_diff"
            ),
        },
    )
