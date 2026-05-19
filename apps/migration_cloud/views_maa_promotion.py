"""Operator dashboard for the MAA v2.0 promotion path (v3.35.0 Agent 3).

Single staff-only HTML surface that aggregates the data sources the
partner-success / legal-operations team needs to drive the
``RMC_MAA_DEFAULT_VERSION=v2.0`` flip described in
``docs/MAA_V2_PROMOTION_CHECKLIST.md``.

Panels:

  1. **Readiness** — runs the pre-flight verifier
     (``scripts/verify_maa_v2_promotion_readiness.py``) in-process via
     its ``run_all_checks()`` callable, so no subprocess + no user
     input is shelled out. Output is a structured per-check list.
  2. **Draft status** — reads the live (in-process) values of
     ``settings.MIGRATION_CLOUD_MAA_DEFAULT_VERSION`` and the
     ``MAA_TEXT_DRAFT_VERSIONS`` set from
     ``apps.migration_cloud.services.maa_text``.
  3. **Counsel attestations** — most-recent
     ``MigrationCloudCounselAttestation`` rows (no attestation_hash
     bytes logged; only counts + per-type aggregates + recent rows).
  4. **Campaign progress** — aggregate counts from
     ``MigrationCloudMAACampaignNotification`` grouped by
     ``dispatch_mode``.

Permission model: ``@staff_member_required`` via
``method_decorator(..., name="dispatch")``. The URL pattern carries
``# rbac-allow: super-staff-view-maa-promotion-status`` so the
RBAC matrix records the intentional staff-only gate.

NEVER logged: MAA body content, signature_text bytes, sha256 bytes,
attestation_hash bytes. Only counts + booleans + type aggregates.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View

logger = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load_verifier_module():
    """Import the verifier script as a module without bootstrapping Django twice.

    The verifier is a stdlib-only script under ``scripts/``; it is not
    on the import path. We add ``scripts/`` to ``sys.path`` lazily here
    (idempotent) so ``run_all_checks()`` and the helper readers are
    callable in-process.
    """
    s = str(SCRIPTS_DIR)
    if s not in sys.path:
        sys.path.insert(0, s)
    import verify_maa_v2_promotion_readiness as verifier  # noqa: WPS433

    return verifier


def _run_verifier_in_process() -> dict[str, Any]:
    """Call the verifier's ``run_all_checks`` and return its dict report.

    On any unexpected import or runtime failure we DO NOT raise out of
    the view; we degrade to a single synthesized ``verifier_error``
    check so the dashboard still renders.
    """
    try:
        verifier = _load_verifier_module()
        return verifier.run_all_checks()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "maa_v2_promotion_dashboard_verifier_load_failed exc_type=%s",
            type(exc).__name__,
        )
        return {
            "schema_version": 1,
            "tool": "verify_maa_v2_promotion_readiness.py",
            "generated_at_utc": "",
            "ok": False,
            "fail_count": 1,
            "ok_count": 0,
            "total_count": 1,
            "checks": [
                {
                    "id": "verifier_load",
                    "ok": False,
                    "note": (
                        f"verifier module could not be loaded: "
                        f"{type(exc).__name__}"
                    ),
                },
            ],
        }


def _draft_status_panel() -> dict[str, Any]:
    """Read in-process draft set + default version (no Python exec)."""
    default_version = getattr(
        settings, "MIGRATION_CLOUD_MAA_DEFAULT_VERSION", "v1.0",
    )
    try:
        from apps.migration_cloud.services.maa_text import (
            MAA_TEXT_DRAFT_VERSIONS,
        )
        draft_set = sorted(MAA_TEXT_DRAFT_VERSIONS)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "maa_v2_promotion_dashboard_draft_set_unreadable exc_type=%s",
            type(exc).__name__,
        )
        draft_set = []

    v2_still_draft = "v2.0" in draft_set
    default_is_v1 = default_version == "v1.0"
    default_is_v2 = default_version == "v2.0"
    return {
        "default_version": default_version,
        "draft_set": draft_set,
        "v2_still_draft": v2_still_draft,
        "default_is_v1": default_is_v1,
        "default_is_v2": default_is_v2,
        "promotion_complete": (default_is_v2 and not v2_still_draft),
    }


def _counsel_attestations_panel(limit: int = 25) -> dict[str, Any]:
    """Return recent attestation rows + per-type aggregate counts.

    Never reads attestation_hash bytes (the model carries an audit row
    pointer to ``related_artifact_path`` instead). All cross-tenant
    aggregation is intentional — these rows are platform-wide.
    """
    from collections import Counter

    try:
        from apps.migration_cloud.models import (
            MigrationCloudCounselAttestation,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "maa_v2_promotion_dashboard_attestation_unreadable exc_type=%s",
            type(exc).__name__,
        )
        return {"total": 0, "recent": [], "by_type": [], "load_error": True}

    # tenant-isolation-allow: platform-wide-counsel-attestation-audit-log
    qs = MigrationCloudCounselAttestation.objects.select_related(
        "operator",
    ).order_by("-attested_at")
    # tenant-isolation-allow: platform-wide-counsel-attestation-audit-log
    total = qs.count()
    recent_rows = list(qs[:limit])
    by_type: Counter[str] = Counter()
    # tenant-isolation-allow: platform-wide-counsel-attestation-audit-log
    for row in qs.values_list("attestation_type", flat=True):
        by_type[row] += 1

    recent = []
    for r in recent_rows:
        operator_label = ""
        op = getattr(r, "operator", None)
        if op is not None:
            operator_label = (
                getattr(op, "get_username", lambda: f"user#{r.operator_id}")()
            )
        recent.append({
            "id": r.pk,
            "attestation_type": r.attestation_type,
            "attested_at": r.attested_at,
            "operator_label": operator_label,
            "related_artifact_path": r.related_artifact_path,
            # NOTE: attestation_text rendered separately in the
            # template with |truncatewords:30 so the dashboard does
            # not flash a wall of operator narrative.
            "attestation_text": r.attestation_text,
        })
    return {
        "total": total,
        "recent": recent,
        "by_type": sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0])),
        "load_error": False,
    }


def _campaign_progress_panel() -> dict[str, Any]:
    """Aggregate ``MigrationCloudMAACampaignNotification`` rows.

    Reports: total rows + per-(campaign_version, dispatch_mode)
    counts + per-campaign distinct-agreement reach. NEVER reads
    recipient_email values into the response — only counts.
    """
    from collections import defaultdict

    try:
        from apps.migration_cloud.models import (
            MigrationCloudMAACampaignNotification,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "maa_v2_promotion_dashboard_campaign_unreadable exc_type=%s",
            type(exc).__name__,
        )
        return {"total": 0, "by_campaign": [], "load_error": True}

    # tenant-isolation-allow: cross-tenant-maa-campaign-tracking
    qs = MigrationCloudMAACampaignNotification.objects.all()
    # tenant-isolation-allow: cross-tenant-maa-campaign-tracking
    total = qs.count()

    aggregate: dict[str, dict[str, int]] = defaultdict(
        lambda: {"dry_run": 0, "queued": 0, "agreement_ids": set()},  # type: ignore[dict-item]
    )
    # tenant-isolation-allow: cross-tenant-maa-campaign-tracking
    for cv, mode, aid in qs.values_list(
        "campaign_version", "dispatch_mode", "agreement_id",
    ):
        bucket = aggregate[cv]
        if mode == "queued":
            bucket["queued"] = int(bucket["queued"]) + 1
        else:
            bucket["dry_run"] = int(bucket["dry_run"]) + 1
        bucket["agreement_ids"].add(aid)  # type: ignore[attr-defined]

    by_campaign = []
    for cv in sorted(aggregate.keys()):
        bucket = aggregate[cv]
        by_campaign.append({
            "campaign_version": cv,
            "dry_run": int(bucket["dry_run"]),
            "queued": int(bucket["queued"]),
            "distinct_agreements": len(bucket["agreement_ids"]),  # type: ignore[arg-type]
        })
    return {"total": total, "by_campaign": by_campaign, "load_error": False}


@method_decorator(staff_member_required, name="dispatch")
class MAA_V2_PromotionDashboardView(View):
    """GET /super/migration/maa-v2-promotion/ — staff-only promotion dashboard.

    All four panels rendered on a single GET; no POST surface (the
    flip itself is an out-of-band procedure per the checklist).
    """

    template_name = "migration_cloud/super/maa_v2_promotion.html"

    def get(self, request, *args, **kwargs):
        report = _run_verifier_in_process()
        draft_status = _draft_status_panel()
        attestations = _counsel_attestations_panel()
        campaign = _campaign_progress_panel()

        logger.info(
            "maa_v2_promotion_dashboard_view user_id=%s "
            "verifier_ok=%s fail_count=%s draft_v2=%s default_version=%s "
            "attestation_total=%s campaign_total=%s",
            request.user.pk,
            report.get("ok"),
            report.get("fail_count"),
            draft_status["v2_still_draft"],
            draft_status["default_version"],
            attestations["total"],
            campaign["total"],
        )

        ctx = {
            "shell": kwargs.get("shell", "super"),
            "page_title": "Migration Cloud — MAA v2.0 promotion status",
            "report": report,
            "draft_status": draft_status,
            "attestations": attestations,
            "campaign": campaign,
            "checklist_doc_path": "docs/MAA_V2_PROMOTION_CHECKLIST.md",
        }
        return render(request, self.template_name, ctx)
