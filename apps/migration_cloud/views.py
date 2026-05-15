"""Migration Cloud wizard views (operator + tenant surfaces).

Routes a single bundle through its lifecycle states with one URL per
state transition. All views are class-based, login-required, and respect
both operator (super) and tenant-admin (portal) entry points via the
``shell`` URL kwarg.

This is the Phase U6 scaffold — the surface that Phase U6 finishes with
drag-and-drop, side-by-side preview, and Apple-tier grammar. The
endpoints + routing + state-machine wiring all land here so the UI team
can iterate templates without touching views.

URL grammar (one router, two mount points):

    /super/migration/                      — operator console (list)
    /super/migration/<bundle_id>/          — detail / mapping wizard
    /super/migration/<bundle_id>/apply/    — POST → apply step (dry-run by default)
    /super/migration/<bundle_id>/reconcile/— POST → generate reconciliation report
    /super/migration/<bundle_id>/feedback/ — POST → operator override → record_feedback

    /portal/configure/migration/           — tenant mirror (plan-gated)
    ...same suffixes...
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from .ai_bridge import AIProposal, record_operator_feedback, remember_mapping_decision
from .models import BundleStatus, MigrationBundle

logger = logging.getLogger(__name__)


def _enforce_portal_entitlement(request, shell: str) -> JsonResponse | None:
    """Block tenant entry without the migration_cloud entitlement.

    Operator shell (``shell == "super"``) is always allowed for staff.
    Portal shell consults ``apps.billing`` if available; missing billing
    app degrades to "allow" so dev / pre-billing environments still work.
    Returns ``None`` when the request is allowed; a 402 JsonResponse to
    short-circuit otherwise.
    """
    if shell != "portal":
        return None
    school = getattr(request, "school", None) or getattr(request, "tenant", None)
    if school is None:
        return None
    try:
        from apps.billing.entitlements import can as has_capability
    except Exception:  # noqa: BLE001
        return None
    try:
        if has_capability(school, "migration_cloud"):
            return None
    except Exception:  # noqa: BLE001 — broken billing should never lock out the wizard
        return None
    return JsonResponse(
        {"error": "migration_cloud entitlement required for tenant access"},
        status=402,
    )


class MigrationCloudConsoleView(LoginRequiredMixin, View):
    """List recent bundles for the active shell + intake CTA."""

    template_name = "migration_cloud/console.html"

    def get(self, request, shell: str = "super"):
        gate = _enforce_portal_entitlement(request, shell)
        if gate is not None:
            return gate
        bundles = (
            MigrationBundle.objects
            .order_by("-created_at")
            .select_related("school", "triggered_by")[:50]
        )
        if shell == "portal":
            # Tenant scope: limit to the active school only.
            school = getattr(request, "school", None) or getattr(request, "tenant", None)
            if school is not None:
                bundles = bundles.filter(school=school)
        return render(
            request,
            self.template_name,
            {
                "shell": shell,
                "bundles": bundles,
                "page_title": "Migration Cloud",
            },
        )


class MigrationCloudBundleDetailView(LoginRequiredMixin, View):
    """Show one bundle's profile / classification / mapping / reconciliation surfaces."""

    template_name = "migration_cloud/bundle_detail.html"

    def get(self, request, bundle_id: int, shell: str = "super"):
        bundle = get_object_or_404(MigrationBundle, pk=bundle_id)
        per_artifact_domain = (
            (bundle.discovery_summary or {}).get("per_artifact_domain") or {}
        )
        per_artifact_mappings = (bundle.mapping_summary or {}).get("per_artifact") or {}
        return render(
            request,
            self.template_name,
            {
                "shell": shell,
                "bundle": bundle,
                "artifacts": bundle.artifacts.all(),
                "per_artifact_domain": per_artifact_domain,
                "per_artifact_mappings": per_artifact_mappings,
                "reconciliation": bundle.reconciliation_summary or {},
                "page_title": bundle.label or bundle.idempotency_key,
                "can_apply": bundle.status == BundleStatus.MAPPED,
                "can_reconcile": bundle.status == BundleStatus.APPLIED,
                "can_advance": bundle.status in (
                    BundleStatus.PENDING,
                    BundleStatus.INGESTING,
                    BundleStatus.PROFILED,
                    BundleStatus.CLASSIFIED,
                ),
            },
        )


class MigrationCloudAdvanceView(LoginRequiredMixin, View):
    """POST endpoint: advance bundle through profile → classify → map."""

    def post(self, request, bundle_id: int, shell: str = "super"):
        from .pipeline import advance_bundle

        try:
            summary = advance_bundle(bundle_id=bundle_id, use_accelerator=True)
        except MigrationBundle.DoesNotExist:
            return JsonResponse({"error": "bundle not found"}, status=404)
        except Exception as exc:  # noqa: BLE001
            logger.exception("migration_cloud.views: advance failed for bundle %s", bundle_id)
            return JsonResponse({"error": str(exc)}, status=500)
        return JsonResponse(summary)


class MigrationCloudApplyView(LoginRequiredMixin, View):
    """POST endpoint: apply the MAPPED bundle to the tenant (dry-run via ?dry_run=1)."""

    def post(self, request, bundle_id: int, shell: str = "super"):
        from .orchestrator import apply_bundle

        dry_run = str(request.GET.get("dry_run", "")).lower() in ("1", "true", "yes")
        try:
            result = apply_bundle(bundle_id=bundle_id, dry_run=dry_run)
        except MigrationBundle.DoesNotExist:
            return JsonResponse({"error": "bundle not found"}, status=404)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=409)
        except Exception as exc:  # noqa: BLE001
            logger.exception("migration_cloud.views: apply failed for bundle %s", bundle_id)
            return JsonResponse({"error": str(exc)}, status=500)
        return JsonResponse({
            "bundle_id": result.bundle_id,
            "dry_run": result.dry_run,
            "status": result.status,
            "totals": {
                "created": result.total_created,
                "updated": result.total_updated,
                "quarantined": result.total_quarantined,
            },
            "per_artifact": [
                {
                    "artifact_id": o.artifact_id,
                    "path": o.path_within_bundle,
                    "domain": o.domain,
                    "status": o.status,
                    "migration_run_id": o.migration_run_id,
                    "created": o.result.created,
                    "updated": o.result.updated,
                    "quarantined": o.result.quarantined,
                }
                for o in result.per_artifact
            ],
        })


class MigrationCloudReconcileView(LoginRequiredMixin, View):
    """POST endpoint: compute reconciliation report for an APPLIED bundle."""

    def post(self, request, bundle_id: int, shell: str = "super"):
        import json

        from .reconciliation import reconcile_bundle

        try:
            payload = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            payload = {}
        cohort = payload.get("cohort") if isinstance(payload.get("cohort"), dict) else None

        try:
            report = reconcile_bundle(bundle_id=bundle_id, cohort=cohort)
        except MigrationBundle.DoesNotExist:
            return JsonResponse({"error": "bundle not found"}, status=404)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=409)
        except Exception as exc:  # noqa: BLE001
            logger.exception("migration_cloud.views: reconcile failed for bundle %s", bundle_id)
            return JsonResponse({"error": str(exc)}, status=500)
        return JsonResponse({
            "bundle_id": report.bundle_id,
            "overall_parity_pct": report.overall_parity_pct,
            "per_domain": [
                {
                    "domain": d.domain,
                    "source_count": d.source_count,
                    "target_created": d.target_created,
                    "target_updated": d.target_updated,
                    "quarantined": d.quarantined,
                    "parity_pct": d.parity_pct,
                    "fill_rate_by_field": d.fill_rate_by_field,
                    "sample_count": len(d.sample_rows),
                }
                for d in report.per_domain
            ],
            "notes": report.notes,
        })


class MigrationCloudFeedbackView(LoginRequiredMixin, View):
    """POST endpoint: record an operator's accept/override decision on an AI proposal.

    Flows back into ``services.ai_gateway.record_feedback`` so the
    platform's daily ``AIGatewayMetric`` rollup picks up acceptance rates
    + manual-correction counts per task type. This is how the AI gets
    *functional* over time — we measure operator trust and iterate
    prompts on the slowest-converging domains.
    """

    def post(self, request, bundle_id: int, shell: str = "super"):
        import json

        try:
            payload = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid JSON"}, status=400)

        bundle = get_object_or_404(MigrationBundle, pk=bundle_id)
        accepted = bool(payload.get("accepted", False))
        manual_correction = bool(payload.get("manual_correction", False))
        prompt_type = str(payload.get("prompt_type") or "migration_cloud.field_mapper")
        tier = str(payload.get("tier") or "unknown")
        confidence = float(payload.get("confidence") or 0.0)
        reasoning = str(payload.get("reasoning") or "")

        proposal = AIProposal(
            answer=payload.get("answer"),
            confidence=confidence,
            reasoning=reasoning,
            raw="",
            provider_meta={"tier": tier},
        )
        record_operator_feedback(
            school=bundle.school,
            proposal=proposal,
            prompt_type=prompt_type,
            accepted=accepted,
            manual_correction=manual_correction,
            request_id=payload.get("request_id"),
        )

        # When the operator accepts a mapping (or supplies a manual correction
        # the operator wants reused), persist into AIEmbeddingStore so the
        # next bundle for this tenant can skip the AI tiebreaker entirely.
        remembered = False
        if (accepted or manual_correction) and prompt_type.endswith("field_mapper"):
            mapping_meta = payload.get("mapping") or {}
            source_column = str(mapping_meta.get("source_column") or "")
            canonical_field = str(payload.get("answer") or mapping_meta.get("canonical_field") or "")
            if source_column and canonical_field:
                source_system = ((bundle.discovery_summary or {}).get("source") or {}).get("chosen")
                remembered = remember_mapping_decision(
                    school=bundle.school,
                    source_column=source_column,
                    sample_values=list(mapping_meta.get("sample_values") or []),
                    canonical_field=canonical_field,
                    domain=str(mapping_meta.get("domain") or ""),
                    confidence=max(confidence, 0.90 if accepted else 0.85),
                    method="operator_accept" if accepted else "operator_correction",
                    transformer=mapping_meta.get("transformer"),
                    source_system=source_system,
                )

        return JsonResponse({
            "bundle_id": bundle.pk,
            "recorded": True,
            "remembered_for_recall": remembered,
            "prompt_type": prompt_type,
            "accepted": accepted,
            "manual_correction": manual_correction,
        })


class MigrationCloudShadowView(LoginRequiredMixin, View):
    """POST endpoint cluster for the shadow-mode lifecycle.

    Action picked from ``?action=`` query string:

        ?action=start     — open a shadow window
        ?action=refresh   — take a tick (compute drift, maybe auto-cutover)
        ?action=close     — seal the window (body ``{"accepted": true/false}``)
        ?action=status    — GET the current state (read-only via POST)

    Source-side counts are operator-supplied in the body
    (``{"source_counts": {"students": 1240, ...}}``) because the platform
    can't assume how the old SIS exposes itself.
    """

    def post(self, request, bundle_id: int, shell: str = "super"):
        import json

        from . import shadow

        try:
            payload = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            payload = {}
        action = (request.GET.get("action") or payload.get("action") or "status").strip().lower()
        source_counts = payload.get("source_counts") if isinstance(payload.get("source_counts"), dict) else None
        source_pull = (lambda c=source_counts: dict(c)) if source_counts is not None else None

        try:
            if action == "start":
                state = shadow.start_shadow_window(
                    bundle_id=bundle_id,
                    target_parity_pct=float(payload.get("target_parity_pct", 99.0)),
                    max_window_hours=int(payload.get("max_window_hours", 168)),
                    auto_cutover_armed=bool(payload.get("auto_cutover_armed", False)),
                    source_pull=source_pull,
                )
            elif action == "refresh":
                state = shadow.refresh_shadow(
                    bundle_id=bundle_id, source_pull=source_pull,
                )
            elif action == "close":
                state = shadow.close_shadow(
                    bundle_id=bundle_id,
                    accepted=bool(payload.get("accepted", False)),
                )
            elif action == "status":
                bundle = get_object_or_404(MigrationBundle, pk=bundle_id)
                state = (bundle.reconciliation_summary or {}).get("shadow") or {}
                return JsonResponse({"bundle_id": bundle.pk, "shadow": state})
            else:
                return JsonResponse({"error": f"unknown action {action!r}"}, status=400)
        except MigrationBundle.DoesNotExist:
            return JsonResponse({"error": "bundle not found"}, status=404)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=409)
        except Exception as exc:  # noqa: BLE001
            logger.exception("migration_cloud.views: shadow %s failed for bundle %s", action, bundle_id)
            return JsonResponse({"error": str(exc)}, status=500)

        from dataclasses import asdict
        return JsonResponse({
            "bundle_id": bundle_id,
            "action": action,
            "shadow": asdict(state),
        })


class MigrationCloudRollbackView(LoginRequiredMixin, View):
    """POST endpoint: roll back one child ``MigrationRun`` of a bundle."""

    def post(self, request, bundle_id: int, run_id: int, shell: str = "super"):
        try:
            from apps.automation.models import MigrationRun
        except ImportError:
            return JsonResponse({"error": "automation app not available"}, status=500)

        run = get_object_or_404(MigrationRun, pk=run_id)
        rollback_run, result = run.trigger_rollback(user=request.user)
        return JsonResponse({
            "bundle_id": bundle_id,
            "run_id": run.pk,
            "rollback_run_id": getattr(rollback_run, "pk", None),
            "result": result,
        })


class MigrationCloudSaveProfileView(LoginRequiredMixin, View):
    """POST endpoint: distill a MAPPED bundle's accepted mappings into a reusable
    ``apps.automation.MigrationProfile`` row.

    Curated profiles beat AI tiebreaker forever: subsequent bundles from the
    same source pre-load the saved column→canonical map and skip discovery
    for known shapes. Tenant-scoped via the bundle's school.
    """

    def post(self, request, bundle_id: int, shell: str = "super"):
        import json
        import re

        try:
            from apps.automation.models import MigrationProfile
        except Exception:  # noqa: BLE001
            return JsonResponse({"error": "automation app not available"}, status=500)

        bundle = get_object_or_404(MigrationBundle, pk=bundle_id)
        try:
            payload = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid JSON"}, status=400)

        name = str(payload.get("name") or "").strip() or (
            bundle.label or f"Profile from bundle {bundle.pk}"
        )
        description = str(payload.get("description") or "").strip()
        source_chosen = ((bundle.discovery_summary or {}).get("source") or {}).get("chosen") or "other"
        domain_hint = str(payload.get("domain") or "generic_sis").lower()

        source_map = {
            "powerschool": MigrationProfile.SourceSystem.POWERSCHOOL,
            "blackbaud": MigrationProfile.SourceSystem.BLACKBAUD,
            "veracross": MigrationProfile.SourceSystem.VERACROSS,
            "infinite_campus": MigrationProfile.SourceSystem.INFINITE_CAMPUS,
            "facts": MigrationProfile.SourceSystem.FACTS,
            "skyward": MigrationProfile.SourceSystem.SKYWARD,
            "alma": MigrationProfile.SourceSystem.ALMA,
        }
        domain_map = {
            "students": MigrationProfile.Domain.STUDENTS,
            "finance": MigrationProfile.Domain.FINANCE,
            "attendance": MigrationProfile.Domain.ATTENDANCE,
            "grades": MigrationProfile.Domain.GRADES,
        }
        source_system_value = source_map.get(source_chosen, MigrationProfile.SourceSystem.OTHER)
        domain_value = domain_map.get(domain_hint, MigrationProfile.Domain.GENERIC_SIS)

        per_artifact = (bundle.mapping_summary or {}).get("per_artifact") or {}
        curated_columns: dict[str, dict[str, Any]] = {}
        for _path, mappings in per_artifact.items():
            for m in (mappings or []):
                src = m.get("source_column")
                cf = m.get("canonical_field")
                if not src or not cf or cf.startswith("custom_fields."):
                    continue
                if float(m.get("confidence") or 0.0) < 0.65:
                    continue
                curated_columns.setdefault(src, {
                    "canonical_field": cf,
                    "transformer": m.get("transformer"),
                    "domain": m.get("domain") or domain_hint,
                    "confidence": m.get("confidence"),
                })

        slug_base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or f"bundle-{bundle.pk}"
        slug = slug_base
        counter = 1
        while MigrationProfile.objects.filter(slug=slug).exists():
            counter += 1
            slug = f"{slug_base}-{counter}"[:64]

        config: dict[str, Any] = {
            "saved_from_bundle_id": bundle.pk,
            "source_chosen": source_chosen,
            "tenant_school_id": str(getattr(bundle.school, "pk", "")) if bundle.school else "",
            "columns": curated_columns,
            "ontology_version": "v1",
        }

        profile = MigrationProfile.objects.create(
            slug=slug,
            source_system=source_system_value,
            profile_category=MigrationProfile.ProfileCategory.STRATEGY,
            name=name,
            description=description or f"Curated from bundle {bundle.label or bundle.pk}",
            format=MigrationProfile.Format.GENERIC_SIS,
            domain=domain_value,
            config=config,
            is_active=True,
        )

        return JsonResponse({
            "profile_slug": profile.slug,
            "profile_id": profile.pk,
            "columns_saved": len(curated_columns),
            "source_system": source_system_value,
            "domain": domain_value,
        })


class MigrationCloudAnomalyNudgeView(LoginRequiredMixin, View):
    """GET endpoint: operator review queue for a bundle.

    Surfaces (a) low-confidence column mappings flagged for human review,
    (b) quarantine records from apply, and (c) reconciliation drift hotspots
    — the three things an operator actually needs to act on. This is the
    "anomaly nudge" surface: actionable items only, no chatter.
    """

    template_name = "migration_cloud/anomaly_nudge.html"

    def get(self, request, bundle_id: int, shell: str = "super"):
        from apps.migration_cloud import defaults as mc_defaults

        bundle = get_object_or_404(MigrationBundle, pk=bundle_id)
        threshold = float(mc_defaults.get("migration_cloud.mapper.field_min_confidence"))

        low_conf_mappings: list[dict[str, Any]] = []
        per_artifact = (bundle.mapping_summary or {}).get("per_artifact") or {}
        for path, mappings in per_artifact.items():
            for m in (mappings or []):
                conf = float(m.get("confidence") or 0.0)
                if conf < threshold or str(m.get("canonical_field") or "").startswith("custom_fields."):
                    low_conf_mappings.append({
                        "artifact": path,
                        "source_column": m.get("source_column"),
                        "canonical_field": m.get("canonical_field"),
                        "confidence": conf,
                        "method": m.get("method"),
                        "transformer": m.get("transformer"),
                        "reasoning": m.get("reasoning"),
                        "domain": m.get("domain"),
                    })

        quarantine_rows: list[dict[str, Any]] = []
        try:
            from apps.automation.models import MigrationQuarantineRecord, MigrationRun

            run_ids = list(
                MigrationRun.objects.filter(parent_bundle_id=bundle.pk).values_list("pk", flat=True)
            )
            for q in MigrationQuarantineRecord.objects.filter(
                migration_run_id__in=run_ids
            ).order_by("-id")[:200]:
                quarantine_rows.append({
                    "id": q.pk,
                    "run_id": q.migration_run_id,
                    "reason": getattr(q, "reason", "") or getattr(q, "error_message", ""),
                    "raw_row": getattr(q, "raw_row", None) or getattr(q, "row_data", None),
                    "ack_status": getattr(q, "exception_ack_status", ""),
                })
        except Exception:  # noqa: BLE001
            logger.debug("anomaly_nudge: quarantine fetch failed", exc_info=True)

        reconciliation = bundle.reconciliation_summary or {}
        drift_domains = [
            d for d in (reconciliation.get("per_domain") or [])
            if float(d.get("parity_pct") or 100.0) < 99.0
        ]

        return render(
            request,
            self.template_name,
            {
                "shell": shell,
                "bundle": bundle,
                "low_conf_mappings": low_conf_mappings,
                "quarantine_rows": quarantine_rows,
                "drift_domains": drift_domains,
                "threshold": threshold,
                "page_title": f"Review queue — {bundle.label or bundle.idempotency_key}",
            },
        )
