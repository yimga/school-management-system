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
    """Dismiss rows that never needed operator action (deleted-in-source, duplicate).

    This is the ONE rule whose evidence is the class itself. The others re-read
    the source row and decide from what is in it, so a mis-guessed class costs
    them nothing; here the class IS the finding, and dismissing on it says "this
    row is already applied, or was never meant to apply" without looking at the
    row at all.

    So it acts only on a class the lander DECLARED. ``orchestrator.py`` records
    ``reason_source`` for exactly this and says so in its own comment: a
    remediation pass must be able to refuse to act automatically on a guess.

    What the guess costs, measured: no lander declares ``DUPLICATE`` anywhere, so
    every row that reaches that class got there through ``classify_message``,
    whose rule is ``"duplicate" in e or "unique" in e or "already exists" in e``.
    That matches a real write FAILURE -- ``UNIQUE constraint failed:
    finance_invoice.reference`` is a row that did not land -- and closed it as
    though it had. A guessed no-action class now keeps the row held for a person,
    which is the correct answer to "we are not sure this landed".
    """
    from apps.automation.quarantine_services import mark_repaired

    qs = quarantine_queryset_for_bundle(bundle, pending_only=True).filter(
        issue_class__in=QUARANTINE_NO_ACTION_CLASSES
    )
    dismissed = 0
    held_on_guess = 0
    for rec in qs.iterator():
        payload = rec.payload if isinstance(rec.payload, dict) else {}
        if str(payload.get("reason_source") or "fallback") != "declared":
            held_on_guess += 1
            continue
        mark_repaired(
            rec,
            {
                "auto_dismissed": True,
                "note": "Auto-dismissed — no import action required",
                "by": getattr(user, "pk", None),
            },
        )
        dismissed += 1
    if held_on_guess:
        logger.info(
            "auto_remediate: bundle %s kept %s no-action row(s) held — the class was "
            "guessed from the error text, not declared by the lander",
            getattr(bundle, "pk", None),
            held_on_guess,
        )
    return {"dismissed": dismissed, "held_on_guessed_class": held_on_guess}


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


def _transformer_options_from_bundle(bundle) -> dict[str, Any]:
    summary = getattr(bundle, "mapping_summary", None) or {}
    prefs = summary.get("transform_prefs") or {}
    return prefs if isinstance(prefs, dict) else {}


def _attempt_land_row_on_domain(
    *,
    bundle,
    record,
    source_row: dict[str, Any],
    domain: str,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Try landing one held row on a specific domain lander."""
    from apps.migration_cloud.landers.base import get_lander
    from apps.migration_cloud.orchestrator import _run_lander_under_schema

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
    """Apply defensible defaults to replayable holds and re-land them.

    Covers ``missing_required`` and ``lander_error`` when enrichment evidence
    exists — many landers declare ``lander_error`` for fixable identity gaps.
    """
    from apps.automation.quarantine_services import mark_repaired

    qs = quarantine_queryset_for_bundle(bundle, pending_only=True).filter(
        issue_class__in=("missing_required", "lander_error")
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

        opts = _transformer_options_from_bundle(bundle)
        school = getattr(bundle, "school", None)
        new_row, evidence = enrich_missing_required_row(
            rec.domain,
            source_row,
            school=school,
            transformer_options=opts,
        )
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


def _row_is_misrouted_subject_catalog(
    *,
    domain: str,
    source_row: dict | None,
    message: str = "",
) -> bool:
    from apps.migration_cloud.ingestion_lexicon import row_looks_like_subject_catalog_entry

    if not isinstance(source_row, dict):
        return False
    msg = (message or "").lower()
    if str(domain or "").strip().lower() == "specialties":
        return row_looks_like_subject_catalog_entry(source_row)
    return "subject catalog entry" in msg and row_looks_like_subject_catalog_entry(source_row)


def auto_reroute_misclassified_catalog_rows(bundle, *, user=None) -> dict[str, Any]:
    """Replay subject-shaped rows held on the specialties domain via academics."""
    from apps.automation.quarantine_services import mark_repaired

    qs = quarantine_queryset_for_bundle(bundle, pending_only=True).filter(
        issue_class="lander_error"
    )
    replayed = 0
    failed = 0
    errors: list[str] = []

    for rec in qs.iterator():
        payload = rec.payload if isinstance(rec.payload, dict) else {}
        source_row = _source_row_from_payload(payload)
        message = str(payload.get("error") or payload.get("message") or "")
        if not _row_is_misrouted_subject_catalog(
            domain=str(rec.domain or ""),
            source_row=source_row,
            message=message,
        ):
            continue

        ok, err = _attempt_land_row_on_domain(
            bundle=bundle,
            record=rec,
            source_row=source_row,
            domain="academics",
        )
        if not ok:
            failed += 1
            if err and len(errors) < 10:
                errors.append(f"record {rec.pk}: {err}")
            continue

        mark_repaired(
            rec,
            {
                "auto_rerouted": True,
                "auto_catalog_reroute": True,
                "note": "Auto-routed subject catalog row from specialties to academics",
                "source_row": source_row,
                "by": getattr(user, "pk", None),
            },
        )
        replayed += 1

    return {"replayed": replayed, "failed": failed, "errors": errors}


def auto_ensure_teaching_graph_closure(bundle, *, user=None) -> dict[str, Any]:
    """Placement, enrollment sync, then teaching grid — full import graph closure."""
    school = getattr(bundle, "school", None)
    if not school:
        return {"skipped": True, "reason": "no_school"}

    from .post_apply_provision import _gap_fill_enabled
    from .post_import_graph_closure import run_post_import_graph_closure

    if not _gap_fill_enabled(school):
        return {"skipped": True, "reason": "gap_fill_disabled"}

    outcome = run_post_import_graph_closure(school, bundle=bundle, dry_run=False)
    summary = dict(getattr(bundle, "mapping_summary", None) or {})
    summary["teaching_graph_closure"] = {
        **outcome,
        "by": getattr(user, "pk", None),
    }
    bundle.mapping_summary = summary
    bundle.save(update_fields=["mapping_summary", "updated_at"])
    return outcome


def auto_ensure_finance_ledger_closure(bundle, *, user=None) -> dict[str, Any]:
    """Issue imported invoices, sync payments, and post ledger entries."""
    school = getattr(bundle, "school", None)
    if not school:
        return {"skipped": True, "reason": "no_school"}

    from .finance_ledger import ensure_finance_ledger_closure_for_bundle
    from .post_apply_provision import _gap_fill_enabled

    if not _gap_fill_enabled(school):
        return {"skipped": True, "reason": "gap_fill_disabled"}

    outcome = ensure_finance_ledger_closure_for_bundle(bundle, dry_run=False)
    summary = dict(getattr(bundle, "mapping_summary", None) or {})
    summary["finance_ledger_closure"] = {
        **outcome,
        "by": getattr(user, "pk", None),
    }
    bundle.mapping_summary = summary
    bundle.save(update_fields=["mapping_summary", "updated_at"])
    return outcome


def auto_repair_inverted_catalog(bundle, *, user=None) -> dict[str, Any]:
    """Remove phantom specialty/department rows that duplicate real subjects."""
    school = getattr(bundle, "school", None)
    if not school:
        return {"skipped": True, "reason": "no_school"}
    from .catalog_repair import (
        auto_repair_inverted_catalog_for_school,
        school_wants_catalog_autorepair,
    )

    if not school_wants_catalog_autorepair(school):
        return {"skipped": True, "reason": "not_tvet_school"}

    outcome = auto_repair_inverted_catalog_for_school(school, dry_run=False)
    plan = outcome.get("plan") or {}
    if not plan.get("actionable"):
        return {"skipped": True, "reason": "no_phantoms", "plan": plan}

    summary = dict(getattr(bundle, "mapping_summary", None) or {})
    summary["catalog_repair"] = {
        **outcome,
        "by": getattr(user, "pk", None),
    }
    bundle.mapping_summary = summary
    bundle.save(update_fields=["mapping_summary", "updated_at"])
    return outcome


def _sum_auto_resolved(results: dict[str, Any]) -> int:
    return (
        int(results.get("informational_dismissed") or 0)
        + int(results.get("pdf_noise_dismissed") or 0)
        + int(results.get("fragment_dismissed") or 0)
        + int(results.get("invalid_ref_replayed") or 0)
        + int(results.get("missing_required_replayed") or 0)
        + int(results.get("catalog_rerouted") or 0)
        + int(results.get("catalog_phantoms_removed") or 0)
        + int(results.get("teacher_assignments_linked") or 0)
        + int(
            (results.get("teaching_graph_closure") or {}).get("teacher_links", {}).get(
                "teacher_assignments_created", 0
            )
            or 0
        )
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


# A held-review page open runs five queryset passes and, for two of them, WRITES
# (rows are re-landed). Bundle 83 on production carries 75,600 pending rows, so
# 'however many there are' is not a budget -- that request would burn a worker
# until the proxy killed it, and a reload would burn another. Above this many
# pending rows the pass is a batch job, not a page-open side effect.
REVIEW_OPEN_ROW_BUDGET = 5000  # magic-number-allow: autopilot-rows-per-page-open

# The preview reports EXACT counts for every pending row, but keeps per-row
# detail for only this many -- the detail exists to eyeball, and 75,600 dicts
# is an out-of-memory kill, not an answer.
PREVIEW_ROW_SAMPLE_CAP = 1000  # magic-number-allow: preview-rows-sampled


def auto_remediate_on_review_open(
    bundle,
    *,
    user=None,
    skip_inference: bool = True,
    enforce_row_budget: bool = True,
) -> dict[str, Any]:
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
    # enforce_row_budget=False is for the batch path, which runs outside any
    # request and therefore has no proxy to be killed by. The budget exists to
    # protect a PAGE OPEN, not to make large bundles unresolvable -- a guard that
    # left 75,600 rows with nowhere to go would just be the old bug, refused
    # politely.
    if pending_before == 0:
        results["pending_after"] = 0
        results["auto_resolved_total"] = 0
        return results

    if enforce_row_budget and pending_before > REVIEW_OPEN_ROW_BUDGET:
        # Refuse rather than start something that cannot finish. A pass killed
        # mid-flight by a request timeout leaves SOME rows closed and the rest
        # held, with nothing told to the operator -- worse than not running.
        logger.warning(
            "auto_remediate: bundle %s has %s pending rows (budget %s) -- skipping the page-open pass; run preview_quarantine_autopilot / a batch repair instead",
            getattr(bundle, "pk", None),
            pending_before,
            REVIEW_OPEN_ROW_BUDGET,
        )
        results["skipped_over_budget"] = True
        results["row_budget"] = REVIEW_OPEN_ROW_BUDGET
        results["pending_after"] = pending_before
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
    reroute = auto_reroute_misclassified_catalog_rows(bundle, user=user)
    results["invalid_ref_replayed"] = int(invalid.get("replayed") or 0)
    results["missing_required_replayed"] = int(enrich.get("replayed") or 0)
    results["catalog_rerouted"] = int(reroute.get("replayed") or 0)

    catalog_fix = auto_repair_inverted_catalog(bundle, user=user)
    if catalog_fix.get("applied"):
        results["catalog_phantoms_removed"] = int(
            catalog_fix.get("phantom_specialties_removed") or 0
        ) + int(catalog_fix.get("phantom_departments_removed") or 0)
        results["catalog_repair"] = catalog_fix
        post_invalid = auto_replay_invalid_ref_holds(bundle, user=user)
        post_enrich = auto_enrich_and_replay_missing_required(bundle, user=user)
        results["invalid_ref_replayed"] = int(results["invalid_ref_replayed"]) + int(
            post_invalid.get("replayed") or 0
        )
        results["missing_required_replayed"] = int(
            results["missing_required_replayed"]
        ) + int(post_enrich.get("replayed") or 0)
        results["post_catalog_replay"] = {
            "invalid_ref": post_invalid,
            "enrich": post_enrich,
        }

    graph_closure = auto_ensure_teaching_graph_closure(bundle, user=user)
    results["teaching_graph_closure"] = graph_closure
    if graph_closure and not graph_closure.get("skipped"):
        post_graph_invalid = auto_replay_invalid_ref_holds(bundle, user=user)
        results["invalid_ref_replayed"] = int(results["invalid_ref_replayed"]) + int(
            post_graph_invalid.get("replayed") or 0
        )
        results["post_teaching_graph_replay"] = post_graph_invalid

    finance_closure = auto_ensure_finance_ledger_closure(bundle, user=user)
    results["finance_ledger_closure"] = finance_closure

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
        reroute = auto_reroute_misclassified_catalog_rows(bundle, user=user)
        results[f"invalid_ref_pass_{pass_num}"] = invalid
        results[f"enrich_pass_{pass_num}"] = enrich
        results[f"catalog_reroute_pass_{pass_num}"] = reroute
        if (
            int(invalid.get("replayed") or 0)
            + int(enrich.get("replayed") or 0)
            + int(reroute.get("replayed") or 0)
        ) == 0:
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
    reroute_total = sum(
        int((results.get(f"catalog_reroute_pass_{n}") or {}).get("replayed") or 0)
        for n in range(1, MAX_AUTO_REMEDIATE_PASSES + 1)
    )
    results["invalid_ref_replayed"] = invalid_total
    results["missing_required_replayed"] = enrich_total
    results["catalog_rerouted"] = reroute_total

    catalog_fix = auto_repair_inverted_catalog(bundle, user=user)
    if catalog_fix.get("applied"):
        results["catalog_phantoms_removed"] = int(
            catalog_fix.get("phantom_specialties_removed") or 0
        ) + int(catalog_fix.get("phantom_departments_removed") or 0)
        results["catalog_repair"] = catalog_fix
        post_invalid = auto_replay_invalid_ref_holds(bundle, user=user)
        post_enrich = auto_enrich_and_replay_missing_required(bundle, user=user)
        results["invalid_ref_replayed"] = int(results["invalid_ref_replayed"]) + int(
            post_invalid.get("replayed") or 0
        )
        results["missing_required_replayed"] = int(
            results["missing_required_replayed"]
        ) + int(post_enrich.get("replayed") or 0)
        results["post_catalog_replay"] = {
            "invalid_ref": post_invalid,
            "enrich": post_enrich,
        }

    graph_closure = auto_ensure_teaching_graph_closure(bundle, user=user)
    results["teaching_graph_closure"] = graph_closure
    if graph_closure and not graph_closure.get("skipped"):
        post_graph_invalid = auto_replay_invalid_ref_holds(bundle, user=user)
        results["invalid_ref_replayed"] = int(results["invalid_ref_replayed"]) + int(
            post_graph_invalid.get("replayed") or 0
        )
        results["post_teaching_graph_replay"] = post_graph_invalid

    finance_closure = auto_ensure_finance_ledger_closure(bundle, user=user)
    results["finance_ledger_closure"] = finance_closure

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
    pending = 0
    counts: dict[str, int] = {"auto_close": 0, "auto_replay": 0, "needs_person": 0}
    by_rule: dict[str, int] = {}
    held_breakdown: dict[str, int] = {}
    guessed_class_auto = 0
    held_on_guess = 0

    for rec in quarantine_queryset_for_bundle(bundle, pending_only=True).iterator():
        payload = rec.payload if isinstance(rec.payload, dict) else {}
        source_row = _source_row_from_payload(payload)
        artifact = str(payload.get("artifact") or "")
        issue_class = str(rec.issue_class or "")
        domain = str(rec.domain or "")
        reason_source = str(payload.get("reason_source") or "fallback")
        message = str(payload.get("error") or payload.get("message") or "")

        outcome, rule, detail = _preview_one(
            issue_class=issue_class,
            domain=domain,
            source_row=source_row,
            artifact=artifact,
            reason_source=reason_source,
            bundle=bundle,
            message=message,
        )

        counts[outcome] += 1
        by_rule[rule] = by_rule.get(rule, 0) + 1
        if outcome == "needs_person":
            cell = f"{issue_class}|{domain}|{artifact.rsplit('/', 1)[-1] or '—'}"
            held_breakdown[cell] = held_breakdown.get(cell, 0) + 1
            if rule == "guessed_no_action":
                held_on_guess += 1
        elif reason_source != "declared":
            # The class this decision rests on was GUESSED from the error text.
            # orchestrator.py's own comment says a remediation pass should be able
            # to refuse to act on a guess; nothing does yet, so at least count it.
            guessed_class_auto += 1

        pending += 1
        if len(rows) >= PREVIEW_ROW_SAMPLE_CAP:
            # The counts above are exact; only the per-row DETAIL is sampled.
            # iterator() was chosen so the queryset is not held in memory, and
            # accumulating a dict per row put it straight back.
            continue
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
        "pending": pending,
        "counts": counts,
        "by_rule": dict(sorted(by_rule.items(), key=lambda kv: -kv[1])),
        "needs_person_breakdown": dict(
            sorted(held_breakdown.items(), key=lambda kv: -kv[1])
        ),
        "auto_decided_on_guessed_class": guessed_class_auto,
        "held_because_class_was_guessed": held_on_guess,
        "rows": rows,
        "rows_returned": len(rows),
        # Never a silent cap: a truncated sample that reads as the whole set
        # would make a partial answer look like a complete one.
        "rows_truncated": max(0, pending - len(rows)),
    }


def _preview_one(
    *,
    issue_class: str,
    domain: str,
    source_row: dict,
    artifact: str,
    reason_source: str,
    bundle=None,
    message: str = "",
) -> tuple[str, str, str]:
    """Mirror of the rule order in ``auto_remediate_on_review_open``. Read-only."""
    school = getattr(bundle, "school", None) if bundle is not None else None
    transformer_options = (
        _transformer_options_from_bundle(bundle) if bundle is not None else None
    )
    if issue_class in QUARANTINE_NO_ACTION_CLASSES:
        if reason_source != "declared":
            return (
                "needs_person",
                "guessed_no_action",
                f"class {issue_class} was guessed from the error text, not declared "
                "by the lander, and a guess is not evidence the row already landed",
            )
        return "auto_close", "informational", "no import action was ever required"

    if issue_class == "missing_required":
        if row_is_pdf_noise_hold(domain, source_row, artifact):
            return "auto_close", "pdf_noise", "PDF line with no importable identity"
        if row_is_unstructured_text_fragment(source_row, artifact=artifact):
            return "auto_close", "fragment", "PDF text fragment, not a record"
        _, evidence = enrich_missing_required_row(
            domain,
            source_row,
            school=school,
            transformer_options=transformer_options,
        )
        if evidence:
            return (
                "auto_replay",
                "enrich_replay",
                "defensible default available: " + "; ".join(evidence),
            )
        return "needs_person", "none", "required field missing with nothing to infer it from"

    if issue_class == "lander_error":
        if _row_is_misrouted_subject_catalog(
            domain=domain, source_row=source_row, message=message
        ):
            return (
                "auto_replay",
                "catalog_reroute",
                "subject catalog row mis-tagged as specialties; replay via academics",
            )
        _, evidence = enrich_missing_required_row(
            domain,
            source_row,
            school=school,
            transformer_options=transformer_options,
        )
        if evidence:
            return (
                "auto_replay",
                "enrich_replay",
                "defensible default available: " + "; ".join(evidence),
            )
        return "needs_person", "none", f"class {issue_class or 'unknown'} has no automated rule"

    if issue_class == "invalid_ref":
        if source_row:
            return (
                "auto_replay",
                "invalid_ref_replay",
                "reference may have landed in a later wave; row is re-landed",
            )
        return "needs_person", "none", "no source row was kept, so it cannot be replayed"

    return "needs_person", "none", f"class {issue_class or 'unknown'} has no automated rule"
