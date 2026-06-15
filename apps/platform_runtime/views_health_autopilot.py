"""Platform Intelligence & Self-Healing — operator console (Phase 2).

One consolidated operator surface for:
  * AI status & surface inventory (so AI capabilities aren't scattered across dashboards), and
  * the Health Self-Healing engine — live shadow proposals, enabled policies, the curated
    reversible remediation catalog, and the school-attributed remediation log.

Staff-only. The GET page is read-only: computing proposals NEVER mutates tenant state (it
calls the engine's *propose* path, not apply). Autonomous applies still happen only via an
autopilot policy + the sweep command. The page also exposes ONE write action —
``health_autopilot_apply`` (POST) — a human-authorized one-shot apply of a curated reversible
kind; the staff member's explicit click is the authorization, and it is fully audited.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_POST

from apps.platform_runtime import health_autopilot as ha

logger = logging.getLogger(__name__)

# Posture-strip lookback window for the "healed in the last day" counters.
_ACTIVITY_WINDOW_HOURS = 24

_MAX_SCHOOLS_SAMPLED = 50
_MAX_LOG_ROWS = 50
# Anomaly nudges can fire one model call per at-risk tenant when AI is enabled.
# Bound how many tenants we compute nudges for so this staff page never turns into
# an unbounded fan-out of LLM calls; the cap is surfaced honestly in the template.
_MAX_NUDGE_SCHOOLS = 12

# Curated launcher for the genuinely GENERATIVE AI surfaces — the honest answer to
# "where do I actually find AI?". Endpoint-only / ambient surfaces carry route="" so
# we never render a fake link for something that has no standalone page. Routes are
# reversed defensively below (a name may live on a different host's urlconf).
_GENERATIVE_SURFACES = (
    {
        "label": _("AI governance & assistants"),
        "where": _("Tenant · AI governance page"),
        "route": "siteconfig:ai_governance",
        "note": _("Provider posture, the assistant registry, and the (rules-based) policy matrix lookup."),
    },
    {
        "label": _("Studio OS copilot rail"),
        "where": _("Studio workspace"),
        "route": "studio_os:shell",
        "note": _("The primary generative assistant — chat, insights, and drafting."),
    },
    {
        "label": _("Assist dock AI actions"),
        "where": _("Every page · ambient dock"),
        "route": "",
        "note": _("Summarize / explain / draft / translate in place. Ambient — no standalone page."),
    },
    {
        "label": _("Portal AI gateway (legacy)"),
        "where": _("Tenant portal · floating copilot"),
        "route": "",
        "note": _("Legacy streaming copilot, superseded by the Studio rail. Ambient — no standalone page."),
    },
)


def _safe_reverse(name: str) -> str | None:
    if not name:
        return None
    try:
        return reverse(name)
    except Exception:  # noqa: BLE001 — route may live on another host's urlconf
        return None


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
    # Cross-tenant anomaly risk nudges — the same engine that renders on each
    # dashboard, consolidated here read-only (additive: the ambient per-dashboard
    # nudge stays where it proactively helps).
    anomaly_nudges: list[dict] = []
    nudge_attempts = 0
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
            if nudge_attempts < _MAX_NUDGE_SCHOOLS:
                nudge_attempts += 1
                try:
                    from apps.platform_runtime.ai_system_layer import (
                        generate_anomaly_risk_nudge,
                    )

                    nudge = generate_anomaly_risk_nudge(school, getattr(request, "user", None))
                    if nudge:
                        key = str(nudge.get("recommendation_key") or "")
                        anomaly_nudges.append(
                            {
                                "school_slug": getattr(school, "slug", "") or "—",
                                "title": nudge.get("title", ""),
                                "explanation": nudge.get("explanation", ""),
                                "confidence": nudge.get("confidence"),
                                "source": "rules" if key.endswith("rules") else "ai",
                            }
                        )
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "health_autopilot_console: anomaly nudge failed", exc_info=True
                    )
    except Exception:  # noqa: BLE001
        logger.debug("health_autopilot_console: school sampling failed", exc_info=True)

    nudge_scan_capped = sampled > _MAX_NUDGE_SCHOOLS

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
            HealthRemediationLog.objects.all()[:_MAX_LOG_ROWS].values(  # tenant-isolation-allow: super-staff-health-autopilot-cross-tenant-log-sample
                "school_slug", "signal", "kind", "source", "mode", "outcome", "created_at"
            )
        )
    except Exception:  # noqa: BLE001
        logger.debug("health_autopilot_console: policy/log read failed", exc_info=True)

    # --- Posture strip (read-only aggregates over the activity window) ---
    actionable = sum(1 for p in proposals if p.get("available"))
    auto_healed_window = 0
    manual_healed_window = 0
    failures_window = 0
    try:
        from apps.platform_runtime.models import HealthRemediationLog

        since = timezone.now() - timedelta(hours=_ACTIVITY_WINDOW_HOURS)
        log_qs = HealthRemediationLog.objects
        auto_healed_window = log_qs.filter(created_at__gte=since, mode="apply", outcome="applied").count()  # tenant-isolation-allow: super-staff-health-autopilot-cross-tenant-posture-aggregate
        manual_healed_window = log_qs.filter(created_at__gte=since, mode="manual", outcome="applied").count()  # tenant-isolation-allow: super-staff-health-autopilot-cross-tenant-posture-aggregate
        failures_window = log_qs.filter(created_at__gte=since, outcome="failed").count()  # tenant-isolation-allow: super-staff-health-autopilot-cross-tenant-posture-aggregate
    except Exception:  # noqa: BLE001
        logger.debug("health_autopilot_console: posture aggregate failed", exc_info=True)

    # --- Action flash (set by the apply POST redirect; display-only) ---
    flash = None
    flash_outcome = request.GET.get("flash_outcome")
    if flash_outcome:
        flash = {
            "signal": request.GET.get("flash_signal", ""),
            "kind": request.GET.get("flash_kind", ""),
            "tenant": request.GET.get("flash_tenant", ""),
            "outcome": flash_outcome,
            "ok": flash_outcome == "applied",
        }

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

    generative_surfaces = [
        {
            "label": s["label"],
            "where": s["where"],
            "note": s["note"],
            "url": _safe_reverse(s["route"]),
        }
        for s in _GENERATIVE_SURFACES
    ]

    return render(
        request,
        "platform_runtime/health_autopilot_console.html",
        {
            "proposals": proposals,
            "generative_surfaces": generative_surfaces,
            "anomaly_nudges": anomaly_nudges,
            "nudge_scan_capped": nudge_scan_capped,
            "max_nudge_schools": _MAX_NUDGE_SCHOOLS,
            "policies": policies,
            "recent_log": recent_log,
            "catalog": catalog,
            "ai_enabled": ai_enabled,
            "ai_surfaces": ai_surfaces,
            "ai_min_confidence": ha.AI_MIN_CONFIDENCE,
            "schools_sampled": sampled,
            "sampling_truncated": truncated,
            "max_sampled": _MAX_SCHOOLS_SAMPLED,
            # Posture strip + action flash.
            "actionable": actionable,
            "auto_healed_window": auto_healed_window,
            "manual_healed_window": manual_healed_window,
            "failures_window": failures_window,
            "activity_window_hours": _ACTIVITY_WINDOW_HOURS,
            "apply_url": reverse("platform_runtime:health_autopilot_apply"),
            "flash": flash,
        },
    )


@staff_member_required
@require_POST
def health_autopilot_apply(request):
    """Human-authorized one-shot apply of a curated reversible remediation.

    The autonomous engine stays shadow-only and policy-gated; THIS endpoint is the operator's
    in-console counterpart — a staff member explicitly healing one tenant/scope. It delegates
    to ``health_autopilot.apply_manual_remediation`` (only curated reversible kinds are ever
    applied; every apply is audited) and always redirects back to the console with a flash
    describing the outcome.
    """
    signal = (request.POST.get("signal") or "").strip()
    scope = (request.POST.get("scope") or "").strip()
    school_slug = (request.POST.get("school_slug") or "").strip()

    school = None
    if scope == "school" and school_slug and school_slug != "—":
        try:
            from apps.schools.models import School

            school = School.objects.filter(slug=school_slug, is_active=True).first()
        except Exception:  # noqa: BLE001
            logger.debug("health_autopilot_apply: school lookup failed", exc_info=True)
            school = None

    user = getattr(request, "user", None)
    result = ha.apply_manual_remediation(
        signal=signal,
        school=school,
        user=user,
        actor_user_id=str(getattr(user, "pk", "") or ""),
    )

    if result.get("applied"):
        outcome = "applied"
    else:
        outcome = result.get("reason") or result.get("verdict") or "not_applied"

    params = urlencode(
        {
            "flash_signal": signal,
            "flash_kind": result.get("kind") or "",
            "flash_tenant": school_slug or "—",
            "flash_outcome": outcome,
        }
    )
    base = reverse("platform_runtime:health_autopilot_console")
    return redirect(f"{base}?{params}")
