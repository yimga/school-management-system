"""Platform Intelligence & Self-Healing — operator console (Phase 2).

One consolidated operator surface for:
  * AI status & surface inventory (so AI capabilities aren't scattered across dashboards), and
  * the Health Self-Healing engine — live shadow proposals, enabled policies, the curated
    reversible remediation catalog, and the school-attributed remediation log.

Staff-only, read-only page. Computing proposals here NEVER mutates tenant state (it calls the
engine's *propose* path, not apply); applies happen only via policy + the sweep command.
"""

from __future__ import annotations

import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.platform_runtime import health_autopilot as ha

logger = logging.getLogger(__name__)

_MAX_SCHOOLS_SAMPLED = 50
_MAX_LOG_ROWS = 50


def _proposal_row(prop: dict) -> dict:
    return {
        "signal": prop.get("signal"),
        "kind": prop.get("kind"),
        "source": prop.get("source", "—"),
        "available": prop.get("auto_fix_available", False),
        "label": prop.get("label", ""),
        "confidence": prop.get("confidence"),
    }


@staff_member_required
@require_GET
def health_autopilot_console(request):
    """Consolidated AI + self-healing operator console."""

    # --- Live shadow proposals (read-only; NO writes, NO applies) ---
    proposals: list[dict] = []
    for sig in ha.platform_signals():
        proposals.append(
            {"scope": "platform", "school_slug": "—", **_proposal_row(ha.propose_remediation(sig))}
        )

    sampled = 0
    truncated = False
    try:
        from apps.schools.models import School

        qs = School.objects.filter(is_active=True).order_by("name")
        truncated = qs.count() > _MAX_SCHOOLS_SAMPLED
        for school in qs[:_MAX_SCHOOLS_SAMPLED]:
            sampled += 1
            for sig in ha.iter_school_signals(school):
                proposals.append(
                    {
                        "scope": "school",
                        "school_slug": getattr(school, "slug", "") or "—",
                        **_proposal_row(ha.propose_remediation(sig, school=school)),
                    }
                )
    except Exception:  # noqa: BLE001
        logger.debug("health_autopilot_console: school sampling failed", exc_info=True)

    # --- Enabled policies (the ONLY thing that turns shadow into apply) ---
    policies: list[dict] = []
    recent_log: list[dict] = []
    try:
        from apps.platform_runtime.models import HealthRemediationLog, WorkflowAutopilotPolicy

        policies = list(
            WorkflowAutopilotPolicy.objects.filter(workflow_key=ha.WORKFLOW_KEY).values(
                "tenant_schema", "allowed_auto_fix_kinds", "enabled", "updated_at"
            )
        )
        recent_log = list(
            HealthRemediationLog.objects.all()[:_MAX_LOG_ROWS].values(
                "school_slug", "signal", "kind", "source", "mode", "outcome", "created_at"
            )
        )
    except Exception:  # noqa: BLE001
        logger.debug("health_autopilot_console: policy/log read failed", exc_info=True)

    # --- AI consolidation: one place to see AI on/off + every AI surface ---
    ai_enabled = False
    ai_surfaces: dict[str, str] = {}
    try:
        from apps.platform_runtime.ai_providers import (
            describe_ai_assistant_surfaces,
            get_ai_runtime_config,
        )

        ai_enabled = bool(get_ai_runtime_config().get("enabled"))
        ai_surfaces = describe_ai_assistant_surfaces()
    except Exception:  # noqa: BLE001
        logger.debug("health_autopilot_console: ai status read failed", exc_info=True)

    catalog = [{"kind": k, **v} for k, v in sorted(ha.HEALTH_REMEDIATION_KINDS.items())]

    return render(
        request,
        "platform_runtime/health_autopilot_console.html",
        {
            "proposals": proposals,
            "policies": policies,
            "recent_log": recent_log,
            "catalog": catalog,
            "ai_enabled": ai_enabled,
            "ai_surfaces": ai_surfaces,
            "ai_min_confidence": ha.AI_MIN_CONFIDENCE,
            "schools_sampled": sampled,
            "sampling_truncated": truncated,
            "max_sampled": _MAX_SCHOOLS_SAMPLED,
        },
    )
