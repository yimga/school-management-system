"""Autonomous quarantine triage — zero-touch import closure (spec step 3).

Runs after every live apply and before repair re-import:
  1. Refresh inference + dismiss informational / PDF noise rows
  2. Replay ``invalid_ref`` holds now that later waves have landed
  3. Enrich defensible ``missing_required`` rows and replay
  4. Persist audit summary + ``reconciliation_status`` closure state
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .landers._helpers import (
    enrich_missing_required_row,
    row_is_pdf_noise_hold,
    row_is_unstructured_text_fragment,
)
from .quarantine_resolution import (
    QUARANTINE_NO_ACTION_CLASSES,
    _resolve_lander_domain,
    _source_row_from_payload,
    pending_quarantine_count,
    quarantine_queryset_for_bundle,
)

logger = logging.getLogger(__name__)

# Bounded retry ceiling — see MIGRATION_CLOUD_ZERO_TOUCH_IMPORT_SPEC hard rules.
MAX_AUTO_REMEDIATE_PASSES = 2


def auto_dismiss_informational(bundle, *, user=None) -> dict[str, Any]:
    """Dismiss rows that never needed operator action (deleted-in-source, duplicate)."""
    from apps.automation.quarantine_services import mark_repaired

    qs = quarantine_queryset_for_bundle(bundle, pending_only=True).filter(
        issue_class__in=QUARANTINE_NO_ACTION_CLASSES
    )
    dismissed = 0
    for rec in qs.iterator():
        mark_repaired(
            rec,
            {
                "auto_dismissed": True,
                "note": "Auto-dismissed — no import action required",
                "by": getattr(user, "pk", None),
            },
        )
        dismissed += 1
    return {"dismissed": dismissed}


def auto_dismiss_pdf_noise_holds(bundle, *, user=None) -> dict[str, Any]:
    """Dismiss PDF/stat rows held as missing_required with no domain identity."""
    from apps.automation.quarantine_services import mark_repaired

    qs = quarantine_queryset_for_bundle(bundle, pending_only=True).filter(
        issue_class="missing_required"
    )
    dismissed = 0
    for rec in qs.iterator():
        payload = rec.payload if isinstance(rec.payload, dict) else {}
        source_row = _source_row_from_payload(payload)
        artifact = str(payload.get("artifact") or "")
        if not row_is_pdf_noise_hold(rec.domain, source_row, artifact):
            continue
        mark_repaired(
            rec,
            {
                "auto_dismissed": True,
                "auto_pdf_noise": True,
                "note": "Auto-dismissed — PDF line with no importable identity",
                "by": getattr(user, "pk", None),
            },
        )
        dismissed += 1
    return {"dismissed": dismissed}


def auto_dismiss_unstructured_fragments(bundle, *, user=None) -> dict[str, Any]:
    """Dismiss PDF/stat-sheet text lines that are not importable records."""
    from apps.automation.quarantine_services import mark_repaired

    qs = quarantine_queryset_for_bundle(bundle, pending_only=True).filter(
        issue_class="missing_required"
    )
    dismissed = 0
    for rec in qs.iterator():
        payload = rec.payload if isinstance(rec.payload, dict) else {}
        source_row = _source_row_from_payload(payload)
        artifact = str(payload.get("artifact") or "")
        if not row_is_unstructured_text_fragment(source_row, artifact=artifact):
            continue
        mark_repaired(
            rec,
            {
                "auto_dismissed": True,
                "auto_pdf_fragment": True,
                "note": "Auto-dismissed — PDF text fragment, not an importable record",
                "by": getattr(user, "pk", None),
            },
        )
        dismissed += 1
    return {"dismissed": dismissed}


def _artifact_for_auto_replay(bundle, record) -> Any:
    payload = record.payload if isinstance(record.payload, dict) else {}
    path = str(payload.get("artifact") or "").strip()
    if path:
        art = bundle.artifacts.filter(path_within_bundle=path).first()
        if art is not None:
            return art
    return bundle.artifacts.filter(quarantined=False).order_by("pk").first()


def _attempt_land_quarantine_row(
    *,
    bundle,
    record,
    source_row: dict[str, Any],
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Try landing one held row; returns (success, error_message)."""
    from apps.migration_cloud.landers.base import get_lander
    from apps.migration_cloud.orchestrator import _run_lander_under_schema

    domain = _resolve_lander_domain(record.domain)
    lander = get_lander(domain) or get_lander("custom_fields")
    if lander is None:
        return False, f"no lander for domain {domain!r}"

    artifact = _artifact_for_auto_replay(bundle, record)
    if artifact is None:
        return False, "bundle has no artifact for replay context"

    try:
        result = _run_lander_under_schema(
            lander=lander,
            rows_iter=iter([source_row]),
            bundle=bundle,
            artifact=artifact,
            dry_run=dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"

    if result.quarantined or result.errors:
        err = result.errors[0] if result.errors else "lander quarantined row"
        return False, str(err)
    return True, ""


def auto_replay_invalid_ref_holds(bundle, *, user=None) -> dict[str, Any]:
    """Replay ``invalid_ref`` rows after all dependency waves have finished."""
    from apps.automation.quarantine_services import mark_repaired

    qs = quarantine_queryset_for_bundle(bundle, pending_only=True).filter(
        issue_class="invalid_ref"
    )
    replayed = 0
    failed = 0
    errors: list[str] = []

    for rec in qs.iterator():
        payload = rec.payload if isinstance(rec.payload, dict) else {}
        source_row = _source_row_from_payload(payload)
        if not source_row:
            failed += 1
            continue

        ok, err = _attempt_land_quarantine_row(
            bundle=bundle, record=rec, source_row=source_row
        )
        if not ok:
            failed += 1
            if err and len(errors) < 10:
                errors.append(f"record {rec.pk}: {err}")
            continue

        mark_repaired(
            rec,
            {
                "auto_replayed": True,
                "auto_invalid_ref_wave": True,
                "note": "Auto-replayed — reference resolved after wave order completed",
                "source_row": source_row,
                "by": getattr(user, "pk", None),
            },
        )
        replayed += 1

    return {"replayed": replayed, "failed": failed, "errors": errors}


def auto_enrich_and_replay_missing_required(bundle, *, user=None) -> dict[str, Any]:
    """Apply defensible defaults to ``missing_required`` rows and replay."""
    from apps.automation.quarantine_services import mark_repaired

    qs = quarantine_queryset_for_bundle(bundle, pending_only=True).filter(
        issue_class="missing_required"
    )
    enriched = 0
    replayed = 0
    skipped = 0
    errors: list[str] = []

    for rec in qs.iterator():
        payload = rec.payload if isinstance(rec.payload, dict) else {}
        source_row = _source_row_from_payload(payload)
        artifact = str(payload.get("artifact") or "")
        if row_is_pdf_noise_hold(rec.domain, source_row, artifact):
            skipped += 1
            continue

        new_row, evidence = enrich_missing_required_row(rec.domain, source_row)
        if not evidence:
            skipped += 1
            continue
        enriched += 1

        ok, err = _attempt_land_quarantine_row(
            bundle=bundle, record=rec, source_row=new_row
        )
        if not ok:
            if err and len(errors) < 10:
                errors.append(f"record {rec.pk}: {err}")
            continue

        mark_repaired(
            rec,
            {
                "auto_enriched": True,
                "enrichment_evidence": evidence,
                "note": "Auto-enriched and imported — " + "; ".join(evidence),
                "source_row": new_row,
                "by": getattr(user, "pk", None),
            },
        )
        replayed += 1

    return {
        "enriched": enriched,
        "replayed": replayed,
        "skipped": skipped,
        "errors": errors,
    }


def _sum_auto_resolved(results: dict[str, Any]) -> int:
    return (
        int(results.get("informational_dismissed") or 0)
        + int(results.get("pdf_noise_dismissed") or 0)
        + int(results.get("fragment_dismissed") or 0)
        + int(results.get("invalid_ref_replayed") or 0)
        + int(results.get("missing_required_replayed") or 0)
    )


def persist_auto_remediation_summary(
    bundle, results: dict[str, Any], *, user=None
) -> None:
    """Write the audit trail onto the bundle (never hides rows — records what closed)."""
    summary = dict(getattr(bundle, "mapping_summary", None) or {})
    results = {
        **results,
        "auto_resolved_total": _sum_auto_resolved(results),
        "completed_at": timezone.now().isoformat(),
    }
    summary["auto_remediation"] = results
    bundle.mapping_summary = summary
    bundle.save(update_fields=["mapping_summary", "updated_at"])
    _emit_auto_remediation_audit(bundle, results, user=user)


def _emit_auto_remediation_audit(
    bundle,
    results: dict[str, Any],
    *,
    user=None,
) -> None:
    """Append a tamper-evident audit event for each autopilot pass."""
    resolved = int(results.get("auto_resolved_total") or 0)
    if resolved <= 0:
        return
    try:
        from apps.migration_cloud.models_audit import MigrationCloudAuditEvent

        school = getattr(bundle, "school", None)
        slug = str(getattr(school, "slug", "") or "")
        MigrationCloudAuditEvent.objects.record(
            slug,
            "migration.quarantine.auto_resolved",
            actor=user,
            subject=bundle.pk,
            payload_summary={
                "bundle_id": bundle.pk,
                "trigger": str(results.get("trigger") or "apply"),
                "auto_resolved_total": resolved,
                "informational_dismissed": int(results.get("informational_dismissed") or 0),
                "pdf_noise_dismissed": int(results.get("pdf_noise_dismissed") or 0),
                "fragment_dismissed": int(results.get("fragment_dismissed") or 0),
                "invalid_ref_replayed": int(results.get("invalid_ref_replayed") or 0),
                "missing_required_replayed": int(results.get("missing_required_replayed") or 0),
                "pending_after": int(results.get("pending_after") or 0),
            },
        )
    except Exception:  # noqa: BLE001 — audit failure must not block triage
        logger.warning(
            "auto_remediate: audit emit failed for bundle %s",
            getattr(bundle, "pk", None),
            exc_info=True,
        )


def _financial_guardrail_blocks_closure(bundle) -> bool:
    """True when control totals failed — closure must stay BLOCKED."""
    size = getattr(bundle, "size_summary", None) or {}
    if size.get("financial_guardrail_failed"):
        return True
    report = (getattr(bundle, "mapping_summary", None) or {}).get("financial_guardrail") or {}
    return bool(report) and report.get("ok") is False


def sync_reconciliation_closure(bundle, results: dict[str, Any] | None = None) -> str:
    """Set ``reconciliation_status`` from pending actionable rows + bundle health."""
    from .models import BundleStatus, ReconciliationClosureStatus
    from .models_cutover import cutover_signoff_pending_for_bundle

    pending = pending_quarantine_count(bundle)
    status = getattr(bundle, "status", "") or ""
    cutover_pending = cutover_signoff_pending_for_bundle(bundle)
    guardrail_failed = _financial_guardrail_blocks_closure(bundle)

    if status in (BundleStatus.FAILED, BundleStatus.ABORTED) or guardrail_failed:
        closure = ReconciliationClosureStatus.BLOCKED
    elif pending == 0 and not cutover_pending:
        closure = ReconciliationClosureStatus.CLOSED
    elif pending == 0 and cutover_pending:
        closure = ReconciliationClosureStatus.PENDING_HUMAN
    else:
        actionable = (
            quarantine_queryset_for_bundle(bundle, pending_only=True)
            .exclude(issue_class__in=QUARANTINE_NO_ACTION_CLASSES)
            .exists()
        )
        closure = (
            ReconciliationClosureStatus.PENDING_HUMAN
            if actionable or cutover_pending
            else ReconciliationClosureStatus.CLOSED
        )

    recon = dict(getattr(bundle, "reconciliation_summary", None) or {})
    recon["closure"] = {
        "status": closure,
        "pending_quarantine": pending,
        "auto_resolved_total": int((results or {}).get("auto_resolved_total") or 0),
        "cutover_signoff_pending": cutover_pending,
        "financial_guardrail_failed": guardrail_failed,
        "updated_at": timezone.now().isoformat(),
    }
    bundle.reconciliation_summary = recon
    bundle.reconciliation_status = closure
    bundle.save(
        update_fields=["reconciliation_status", "reconciliation_summary", "updated_at"]
    )
    return closure


def import_closure_banner(bundle) -> dict[str, Any] | None:
    """Tenant-facing copy when autopilot closed the queue without human action."""
    from .models import ReconciliationClosureStatus

    closure = str(getattr(bundle, "reconciliation_status", "") or "")
    auto = (getattr(bundle, "mapping_summary", None) or {}).get("auto_remediation") or {}
    auto_total = int(auto.get("auto_resolved_total") or 0)
    pdf_skipped = int(auto.get("pdf_noise_dismissed") or 0) + int(
        auto.get("fragment_dismissed") or 0
    )
    pending = pending_quarantine_count(bundle)

    if closure != ReconciliationClosureStatus.CLOSED or pending > 0:
        return None
    if auto_total <= 0:
        return {
            "headline": str(_("Import closed — no rows awaiting review")),
            "detail": "",
            "tone": "success",
        }

    if pdf_skipped >= auto_total:
        detail = str(
            _("PDF and stat-sheet lines were skipped — they were not importable records.")
        )
    else:
        detail = str(
            _(
                "%(pdf)s PDF lines skipped; %(replay)s rows auto-imported after "
                "references or missing fields were resolved."
            )
            % {
                "pdf": pdf_skipped,
                "replay": auto_total - pdf_skipped,
            }
        )

    return {
        "headline": str(
            _("Import closed — %(count)s auto-resolved (PDF lines skipped)")
            % {"count": auto_total}
        ),
        "detail": detail,
        "tone": "success",
        "auto_resolved_total": auto_total,
        "pdf_skipped": pdf_skipped,
    }


def auto_remediate_before_repair(bundle, *, user=None) -> dict[str, Any]:
    """Pre-repair dismiss pass (informational + PDF noise)."""
    results: dict[str, Any] = {
        "inference_refreshed": False,
        "informational_dismissed": 0,
        "pdf_noise_dismissed": 0,
        "fragment_dismissed": 0,
        "pending_before": pending_quarantine_count(bundle),
    }
    try:
        from .pipeline import refresh_bundle_inference

        refresh_bundle_inference(bundle_id=bundle.pk, use_accelerator=True)
        results["inference_refreshed"] = True
    except Exception:  # noqa: BLE001 — stale inference must not block repair
        logger.warning(
            "auto_remediate: inference refresh failed for bundle %s",
            bundle.pk,
            exc_info=True,
        )
    dismiss = auto_dismiss_informational(bundle, user=user)
    results["informational_dismissed"] = dismiss["dismissed"]
    pdf_noise = auto_dismiss_pdf_noise_holds(bundle, user=user)
    results["pdf_noise_dismissed"] = pdf_noise["dismissed"]
    fragments = auto_dismiss_unstructured_fragments(bundle, user=user)
    results["fragment_dismissed"] = fragments["dismissed"]
    results["pending_after"] = pending_quarantine_count(bundle)
    return results


def auto_remediate_on_review_open(bundle, *, user=None, skip_inference: bool = True) -> dict[str, Any]:
    """Zero-touch triage when the held-review page opens — no full re-apply.

    Closes PDF noise and replayable rows that were never triaged because apply
    finished before autopilot existed or the operator opened review without repair.
    """
    pending_before = pending_quarantine_count(bundle)
    results: dict[str, Any] = {
        "pending_before": pending_before,
        "inference_refreshed": False,
        "informational_dismissed": 0,
        "pdf_noise_dismissed": 0,
        "fragment_dismissed": 0,
        "invalid_ref_replayed": 0,
        "missing_required_replayed": 0,
        "trigger": "review_open",
    }
    if pending_before == 0:
        results["pending_after"] = 0
        results["auto_resolved_total"] = 0
        return results

    if not skip_inference:
        try:
            from .pipeline import refresh_bundle_inference

            refresh_bundle_inference(bundle_id=bundle.pk, use_accelerator=True)
            results["inference_refreshed"] = True
        except Exception:  # noqa: BLE001
            logger.warning(
                "auto_remediate: review-open inference refresh failed for bundle %s",
                bundle.pk,
                exc_info=True,
            )

    dismiss = auto_dismiss_informational(bundle, user=user)
    results["informational_dismissed"] = dismiss["dismissed"]
    pdf_noise = auto_dismiss_pdf_noise_holds(bundle, user=user)
    results["pdf_noise_dismissed"] = pdf_noise["dismissed"]
    fragments = auto_dismiss_unstructured_fragments(bundle, user=user)
    results["fragment_dismissed"] = fragments["dismissed"]

    invalid = auto_replay_invalid_ref_holds(bundle, user=user)
    enrich = auto_enrich_and_replay_missing_required(bundle, user=user)
    results["invalid_ref_replayed"] = int(invalid.get("replayed") or 0)
    results["missing_required_replayed"] = int(enrich.get("replayed") or 0)

    pdf_final = auto_dismiss_pdf_noise_holds(bundle, user=user)
    frag_final = auto_dismiss_unstructured_fragments(bundle, user=user)
    results["pdf_noise_dismissed"] = int(results["pdf_noise_dismissed"]) + int(
        pdf_final.get("dismissed") or 0
    )
    results["fragment_dismissed"] = int(results["fragment_dismissed"]) + int(
        frag_final.get("dismissed") or 0
    )

    results["pending_after"] = pending_quarantine_count(bundle)
    results["auto_resolved_total"] = _sum_auto_resolved(results)

    persist_auto_remediation_summary(bundle, results, user=user)
    sync_reconciliation_closure(bundle, results)

    logger.info(
        "migration_cloud.auto_remediate_on_review_open: bundle=%s resolved=%s pending=%s",
        bundle.pk,
        results["auto_resolved_total"],
        results["pending_after"],
    )
    return results


def auto_remediate_after_apply(bundle, *, user=None) -> dict[str, Any]:
    """Full zero-touch pass — spec step 3. Runs after every live apply."""
    results = auto_remediate_before_repair(bundle, user=user)

    for pass_num in range(1, MAX_AUTO_REMEDIATE_PASSES + 1):
        invalid = auto_replay_invalid_ref_holds(bundle, user=user)
        enrich = auto_enrich_and_replay_missing_required(bundle, user=user)
        results[f"invalid_ref_pass_{pass_num}"] = invalid
        results[f"enrich_pass_{pass_num}"] = enrich
        if int(invalid.get("replayed") or 0) + int(enrich.get("replayed") or 0) == 0:
            break

    # Aggregate replay counts for UX + audit
    invalid_total = sum(
        int((results.get(f"invalid_ref_pass_{n}") or {}).get("replayed") or 0)
        for n in range(1, MAX_AUTO_REMEDIATE_PASSES + 1)
    )
    enrich_total = sum(
        int((results.get(f"enrich_pass_{n}") or {}).get("replayed") or 0)
        for n in range(1, MAX_AUTO_REMEDIATE_PASSES + 1)
    )
    results["invalid_ref_replayed"] = invalid_total
    results["missing_required_replayed"] = enrich_total

    # Final PDF noise sweep (rows exposed by failed enrich attempts)
    pdf_final = auto_dismiss_pdf_noise_holds(bundle, user=user)
    frag_final = auto_dismiss_unstructured_fragments(bundle, user=user)
    results["pdf_noise_dismissed"] = int(results.get("pdf_noise_dismissed") or 0) + int(
        pdf_final.get("dismissed") or 0
    )
    results["fragment_dismissed"] = int(results.get("fragment_dismissed") or 0) + int(
        frag_final.get("dismissed") or 0
    )

    results["pending_after"] = pending_quarantine_count(bundle)
    results["auto_resolved_total"] = _sum_auto_resolved(results)

    persist_auto_remediation_summary(bundle, results, user=user)
    sync_reconciliation_closure(bundle, results)

    logger.info(
        "migration_cloud.auto_remediate_after_apply: bundle=%s resolved=%s pending=%s",
        bundle.pk,
        results["auto_resolved_total"],
        results["pending_after"],
    )
    return results


def preview_autopilot_decisions(bundle) -> dict[str, Any]:
    """What autopilot WOULD do to every pending held row. Writes nothing.

    The spec's last unchecked rule is "every claim about behaviour is backed by a
    state read, not by reading the code and reasoning about it". You cannot honour
    that with the real pass, because running it to find out changes the answer --
    and on a live tenant it closes rows to find out whether it would close them.

    So this mirrors the same five rules, in the same order, calling the same
    predicates, and reports three outcomes:

    ``auto_close``
        A dismissal rule matches. Certain: the rule takes the row and closes it.
    ``auto_replay``
        A replay rule matches. NOT certain -- the row is re-landed and the land
        can fail, which leaves it held. Counting these as "will clear" is exactly
        the over-claim this preview exists to stop.
    ``needs_person``
        Nothing touches it.

    ``profile_quarantine_distribution`` answers a narrower question -- it counts
    PDF-noise candidates only, which is one of the five rules.

    Drift between this and the engine is caught by a test that runs both against
    the same bundle and requires every ``auto_close`` prediction to have happened.
    """
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {"auto_close": 0, "auto_replay": 0, "needs_person": 0}
    by_rule: dict[str, int] = {}
    held_breakdown: dict[str, int] = {}
    guessed_class_auto = 0

    for rec in quarantine_queryset_for_bundle(bundle, pending_only=True).iterator():
        payload = rec.payload if isinstance(rec.payload, dict) else {}
        source_row = _source_row_from_payload(payload)
        artifact = str(payload.get("artifact") or "")
        issue_class = str(rec.issue_class or "")
        domain = str(rec.domain or "")
        reason_source = str(payload.get("reason_source") or "fallback")

        outcome, rule, detail = _preview_one(
            issue_class=issue_class,
            domain=domain,
            source_row=source_row,
            artifact=artifact,
        )

        counts[outcome] += 1
        by_rule[rule] = by_rule.get(rule, 0) + 1
        if outcome == "needs_person":
            cell = f"{issue_class}|{domain}|{artifact.rsplit('/', 1)[-1] or '—'}"
            held_breakdown[cell] = held_breakdown.get(cell, 0) + 1
        elif reason_source != "declared":
            # The class this decision rests on was GUESSED from the error text.
            # orchestrator.py's own comment says a remediation pass should be able
            # to refuse to act on a guess; nothing does yet, so at least count it.
            guessed_class_auto += 1

        rows.append(
            {
                "record_id": rec.pk,
                "issue_class": issue_class,
                "domain": domain,
                "artifact": artifact,
                "reason_source": reason_source,
                "outcome": outcome,
                "rule": rule,
                "detail": detail,
            }
        )

    return {
        "bundle_id": getattr(bundle, "pk", None),
        "pending": len(rows),
        "counts": counts,
        "by_rule": dict(sorted(by_rule.items(), key=lambda kv: -kv[1])),
        "needs_person_breakdown": dict(
            sorted(held_breakdown.items(), key=lambda kv: -kv[1])
        ),
        "auto_decided_on_guessed_class": guessed_class_auto,
        "rows": rows,
    }


def _preview_one(
    *, issue_class: str, domain: str, source_row: dict, artifact: str
) -> tuple[str, str, str]:
    """Mirror of the rule order in ``auto_remediate_on_review_open``. Read-only."""
    if issue_class in QUARANTINE_NO_ACTION_CLASSES:
        return "auto_close", "informational", "no import action was ever required"

    if issue_class == "missing_required":
        if row_is_pdf_noise_hold(domain, source_row, artifact):
            return "auto_close", "pdf_noise", "PDF line with no importable identity"
        if row_is_unstructured_text_fragment(source_row, artifact=artifact):
            return "auto_close", "fragment", "PDF text fragment, not a record"
        _, evidence = enrich_missing_required_row(domain, source_row)
        if evidence:
            return (
                "auto_replay",
                "enrich_replay",
                "defensible default available: " + "; ".join(evidence),
            )
        return "needs_person", "none", "required field missing with nothing to infer it from"

    if issue_class == "invalid_ref":
        if source_row:
            return (
                "auto_replay",
                "invalid_ref_replay",
                "reference may have landed in a later wave; row is re-landed",
            )
        return "needs_person", "none", "no source row was kept, so it cannot be replayed"

    return "needs_person", "none", f"class {issue_class or 'unknown'} has no automated rule"
