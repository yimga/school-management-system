"""Self-serve intake → bundle → guarded-apply pipeline (audit G-1a).

This is the wiring that lets a school drive its own migration from MAA-signed to a
live cutover with ZERO operator hand-offs — WITHOUT re-implementing any of the
dangerous tenant-write code. Every heavy step delegates to the already-guarded
machinery:

  * ``BundleIngestionService`` — creates the ``MigrationBundle`` + registers the
    uploaded artifacts (idempotent, quarantine-aware).
  * ``connector_bundle_bridge.run_bundle_pipeline(off_http=True)`` — advances the
    bundle to MAPPED and runs a **dry-run** apply on the durable HeavyWorkOutbox,
    producing a preview (``size_summary['last_dry_run']``) with ZERO tenant writes.
  * ``celery_tasks.enqueue_apply(dry_run=False, reconcile_after=True)`` — the REAL
    apply, run through the orchestrator (financial guardrail, atomic mode,
    quarantine, tenant RLS scoping, rollback) on the outbox, then reconciled.

The intake FSM (``MigrationIntakeRequest``) is a thin coordination layer whose
state is DERIVED from the bundle's status by :func:`sync_intake_from_bundle`. The
one transition that is never automatic is
``promotion-pending-approval → promotion-in-progress``: the real apply runs ONLY
after the school explicitly approves (``views_customer.MigrationIntakePromotionApproveView``),
and that approval is itself gated on guardian consent (audit BLOCKER 6). So a
customer click can never land unvalidated or non-consented data.

Concierge intakes (no uploaded bundle) are untouched: every function here no-ops
when ``intake.bundle_id`` is null, so an operator-driven migration is unaffected.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

from django.conf import settings

from ..models import IntakeMethod
from ..models_intake import MigrationIntakeRequest, MigrationIntakeState, MigrationIntakeStateError

logger = logging.getLogger(__name__)


class IntakePipelineError(Exception):
    """Raised for a caller-visible pipeline problem (bad state, rejected upload)."""


_ARCHIVE_SUFFIXES = (".zip", ".tar", ".gz", ".tgz", ".7z")
_DEFAULT_MAX_UPLOAD_BYTES = 64 * 1024 * 1024  # magic-number-allow: self-serve intake upload cap (64 MiB)
_CSV_SNIFF_HEAD_BYTES = 8192  # magic-number-allow: bytes read to sniff CSV/text structure


def _max_upload_bytes() -> int:
    return int(getattr(settings, "MIGRATION_CLOUD_INTAKE_MAX_UPLOAD_BYTES", _DEFAULT_MAX_UPLOAD_BYTES))


def max_upload_display_mb() -> int:
    """The upload cap in whole MiB, for the upload form's helper text."""
    return _max_upload_bytes() // (1024 * 1024)  # magic-number-allow: bytes-per-MiB display


def _safe_filename(name: str) -> str:
    """Strip path components + keep a bounded, filesystem-safe basename."""
    import re

    base = (name or "upload.csv").replace("\\", "/").split("/")[-1]
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "upload.csv"
    return base[:120]  # magic-number-allow: filename length cap


def _read_head(uploaded_file, n: int = _CSV_SNIFF_HEAD_BYTES) -> bytes:
    try:
        uploaded_file.seek(0)
        data = uploaded_file.read(n)
        uploaded_file.seek(0)
    except (AttributeError, ValueError, OSError):
        return b""
    return data or b""


def _read_all(uploaded_file) -> bytes:
    try:
        uploaded_file.seek(0)
        data = uploaded_file.read()
        uploaded_file.seek(0)
    except (AttributeError, ValueError, OSError):
        return b""
    return data or b""


# Control bytes that legitimately appear in text (tab, LF, CR, FF, VT). Any
# OTHER C0 control byte is a strong binary-content signal.
_TEXT_CONTROL_BYTES = frozenset({0x09, 0x0A, 0x0D, 0x0C, 0x0B})
_MAX_BINARY_CONTROL_RATIO = 0.05  # binary-vs-text heuristic (real CSV heads ≈ 0)


def _looks_like_csv(head: bytes) -> bool:
    """True when signature-less bytes look like delimited text, not binary.

    ``latin-1`` decodes ANY byte sequence, so a successful decode alone does not
    prove text. Guard with the classic is-binary heuristic: a NUL byte, or a
    non-trivial fraction of C0 control bytes (outside tab/newline/CR/FF/VT),
    means binary content — never admit it as CSV even if it happens to contain a
    delimiter. Real CSV heads carry ~zero such bytes; a masquerading binary
    carries many.
    """
    if not head:
        return False
    if b"\x00" in head:  # NUL byte ⇒ binary, not a CSV
        return False
    control = sum(1 for b in head if b < 0x20 and b not in _TEXT_CONTROL_BYTES)
    if control / len(head) > _MAX_BINARY_CONTROL_RATIO:
        return False
    text = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = head.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        return False
    return any(delim in text for delim in (",", ";", "\t"))


def _validate_export_upload(uploaded_file) -> None:
    """Validate a self-serve export: a CSV or a ZIP of CSVs.

    The shared A-4 ``validate_uploaded_file`` gate is magic-byte-only and — by
    design (``apps.security.upload_validation.sniff_file_mime`` never sniffs
    text) — cannot accept a plain CSV, which has no signature. So this composes
    the SAME primitives the module exports: the size cap, a magic-byte sniff
    (a ZIP archive is accepted by its ``PK`` signature), a text/CSV structure
    check for signature-less files, and the malware-scan hook — exactly the
    "validate structure at parse time" path the primitive prescribes for CSV.
    Raises :class:`IntakePipelineError`.
    """
    from apps.security.upload_validation import scan_for_malware, sniff_file_mime

    size = int(getattr(uploaded_file, "size", 0) or 0)
    if size <= 0:
        raise IntakePipelineError("the uploaded file is empty")
    if size > _max_upload_bytes():
        raise IntakePipelineError(
            f"the file is too large (limit {max_upload_display_mb()} MB)"
        )

    mime = sniff_file_mime(_read_head(uploaded_file))
    if mime == "application/zip":
        pass  # archive of CSVs — magic-byte validated
    elif mime == "":
        if not _looks_like_csv(_read_head(uploaded_file)):
            raise IntakePipelineError(
                "unsupported file — upload a CSV or a .zip of CSV files"
            )
    else:
        raise IntakePipelineError(
            f"unsupported file type ({mime}) — upload a CSV or a .zip of CSV files"
        )

    # Malware scan only when a scanner is configured (mirrors the shared gate's
    # guard so we don't slurp the whole file into memory for a no-op scan).
    if getattr(settings, "UPLOAD_MALWARE_SCANNER", None) is not None:
        ok, detail = scan_for_malware(_read_all(uploaded_file))
        if not ok:
            raise IntakePipelineError(f"the file failed a security scan: {detail}")


def self_serve_apply_enabled() -> bool:
    """Operator kill-switch for the self-serve upload → apply surface (audit G-1a).

    Defaults to ENABLED — the feature ships live end-to-end. An operator can set
    ``MIGRATION_CLOUD_SELF_SERVE_APPLY_ENABLED = False`` to instantly close the
    customer upload + promotion entry points (the platform's most dangerous
    surface: customer-triggered tenant writes) without a redeploy. Every write
    still flows through dry-run-first, the guardian-consent gate, and the guarded
    orchestrator apply regardless — this is an operational off-ramp, not the only
    safety.
    """
    return bool(getattr(settings, "MIGRATION_CLOUD_SELF_SERVE_APPLY_ENABLED", True))


# ─── Stage 1: upload → bundle → dry-run preview ──────────────────────────


def attach_and_start(
    intake: MigrationIntakeRequest, uploaded_file, *, actor=None,
) -> dict[str, Any]:
    """Validate + ingest an uploaded export into a bundle, then kick the pipeline.

    Only valid from ``maa-signed`` (consent recorded, data not yet provided). The
    upload is validated by the shared A-4 validator, ingested into a new
    ``MigrationBundle`` bound to the intake's tenant, linked onto the intake, and
    the bundle is advanced (off-HTTP) to MAPPED + dry-run preview. Advances the
    intake to ``extraction-in-progress``.

    Raises :class:`IntakePipelineError` on a bad state or a rejected upload.
    """
    if not self_serve_apply_enabled():
        raise IntakePipelineError(
            "self-serve migration upload is currently disabled by the operator"
        )
    if intake.state != MigrationIntakeState.MAA_SIGNED.value:
        raise IntakePipelineError(
            "data can only be uploaded after the agreement is signed"
        )
    if intake.bundle_id:
        raise IntakePipelineError("this migration already has data attached")

    # Size + magic-byte + CSV-structure + malware validation before a byte is
    # trusted (A-4 primitives, composed for CSV/ZIP — see _validate_export_upload).
    _validate_export_upload(uploaded_file)

    # Spool to a temp path the ingestion adapter can read.
    tmpdir = Path(tempfile.mkdtemp(prefix="rmc-intake-"))
    dest = tmpdir / _safe_filename(getattr(uploaded_file, "name", "upload.csv"))
    with dest.open("wb") as handle:
        for chunk in uploaded_file.chunks():
            handle.write(chunk)

    is_archive = dest.suffix.lower() in _ARCHIVE_SUFFIXES
    method = IntakeMethod.ARCHIVE.value if is_archive else IntakeMethod.FILE_UPLOAD.value

    school = intake.tenant
    from ..schema_binding import resolve_school_schema_name
    from ..services import BundleIngestionService, BundleSpec

    schema_name = resolve_school_schema_name(school) or ""
    try:
        result = BundleIngestionService().ingest(
            BundleSpec(
                intake_method=method,
                handle=dest,
                school_id=school.pk,
                schema_name=schema_name,
                label=f"Self-serve migration · {intake.get_vendor_slug_display()}",
                source_hint=intake.vendor_slug,
                idempotency_key=f"intake-{intake.id}",
                triggered_by_id=getattr(actor, "pk", None),
                intake_source_uri=f"intake:{intake.id}",
            )
        )
    except Exception as exc:  # noqa: BLE001 — surface ingest failure to the caller
        logger.warning(
            "migration_cloud.intake_pipeline: ingest failed intake_id=%s err=%s",
            intake.id, type(exc).__name__,
        )
        raise IntakePipelineError(f"could not read the uploaded export: {exc}") from exc

    bundle_id = result.bundle_id
    intake.bundle_id = bundle_id
    intake.save(update_fields=["bundle", "updated_at"])

    # Advance the FSM, then kick advance→MAPPED + dry-run preview on the outbox.
    try:
        intake.advance(MigrationIntakeState.EXTRACTION_IN_PROGRESS.value, actor=actor)
    except MigrationIntakeStateError as exc:
        raise IntakePipelineError(str(exc)) from exc

    from .connector_bundle_bridge import run_bundle_pipeline

    run_bundle_pipeline(
        bundle_id=bundle_id,
        source_hint=intake.vendor_slug,
        dry_run_apply=True,
        off_http=True,
    )
    logger.info(
        "migration_cloud.intake_pipeline: started intake_id=%s bundle_id=%s artifacts=%s",
        intake.id, bundle_id, result.artifacts_registered,
    )
    return {"bundle_id": bundle_id, "artifacts_registered": result.artifacts_registered}


# ─── Stage 2: reconcile intake FSM ← bundle status ───────────────────────

_PIPELINE_VALUES = tuple(
    s.value for s in (
        MigrationIntakeState.INTAKE_DRAFT,
        MigrationIntakeState.MAA_PENDING_COUNSEL,
        MigrationIntakeState.MAA_SIGNED,
        MigrationIntakeState.EXTRACTION_IN_PROGRESS,
        MigrationIntakeState.EXTRACTION_COMPLETE,
        MigrationIntakeState.VALIDATION_IN_PROGRESS,
        MigrationIntakeState.VALIDATION_COMPLETE,
        MigrationIntakeState.PROMOTION_PENDING_APPROVAL,
        MigrationIntakeState.PROMOTION_IN_PROGRESS,
        MigrationIntakeState.COMPLETE,
    )
)


def _reconcile_target(bundle) -> str:
    """Derive the intake state a bundle's status implies."""
    from ..models import BundleStatus

    status = bundle.status
    if status in (BundleStatus.FAILED, BundleStatus.ABORTED):
        return MigrationIntakeState.FAILED.value
    if status == BundleStatus.RECONCILED:
        return MigrationIntakeState.COMPLETE.value
    if status in (BundleStatus.APPLYING, BundleStatus.APPLIED):
        # Real apply is running / done but reconciliation not yet closed.
        return MigrationIntakeState.PROMOTION_IN_PROGRESS.value
    if status == BundleStatus.MAPPED:
        # Dry-run preview present → validated + ready for the school's approval.
        if (bundle.size_summary or {}).get("last_dry_run"):
            return MigrationIntakeState.PROMOTION_PENDING_APPROVAL.value
        return MigrationIntakeState.VALIDATION_IN_PROGRESS.value
    # PENDING / INGESTING / any pre-MAPPED processing state.
    return MigrationIntakeState.EXTRACTION_IN_PROGRESS.value


def sync_intake_from_bundle(intake: MigrationIntakeRequest, *, actor=None) -> Optional[str]:
    """Advance the intake FSM to match its bundle's real status. Returns new state.

    Best-effort, idempotent, no-op for concierge intakes (no bundle) or terminal
    intakes. Walks one legal transition at a time toward the bundle-derived
    target, but NEVER auto-crosses ``promotion-pending-approval →
    promotion-in-progress`` — that is reserved for the school's explicit approval.
    """
    if not intake.bundle_id or intake.is_terminal:
        return None
    bundle = intake.bundle
    if bundle is None:
        return None
    target = _reconcile_target(bundle)

    if target == MigrationIntakeState.FAILED.value:
        try:
            intake.advance(MigrationIntakeState.FAILED.value, actor=actor)
        except MigrationIntakeStateError:
            pass
        return intake.state

    try:
        target_idx = _PIPELINE_VALUES.index(target)
    except ValueError:
        return intake.state

    pending_idx = _PIPELINE_VALUES.index(
        MigrationIntakeState.PROMOTION_PENDING_APPROVAL.value
    )
    in_progress_idx = _PIPELINE_VALUES.index(
        MigrationIntakeState.PROMOTION_IN_PROGRESS.value
    )

    for _ in range(len(_PIPELINE_VALUES)):  # bounded walk
        try:
            cur_idx = _PIPELINE_VALUES.index(intake.state)
        except ValueError:
            break  # off-pipeline / terminal
        if cur_idx >= target_idx:
            break
        nxt = _PIPELINE_VALUES[cur_idx + 1]
        # Reserve the approval crossing for the explicit customer action.
        if cur_idx == pending_idx and (cur_idx + 1) == in_progress_idx:
            break
        ok, _reason = intake.can_advance_to(nxt)
        if not ok:
            break  # e.g. guardian-consent gate not satisfied — park here
        try:
            intake.advance(nxt, actor=actor)
        except MigrationIntakeStateError:
            break
    return intake.state


# ─── Stage 3: promotion (real guarded apply) ─────────────────────────────


def begin_promotion(intake: MigrationIntakeRequest, *, actor=None) -> dict[str, Any]:
    """Enqueue the REAL guarded apply for a self-serve intake after approval.

    Called by the approve view AFTER it has advanced the intake into
    ``promotion-in-progress``. No-op for concierge intakes (no bundle) — an
    operator drives those. The apply runs through the orchestrator's guarded path
    (financial guardrail, atomic, quarantine, RLS, rollback) on the durable
    outbox, then reconciles — never on the HTTP thread.
    """
    if not self_serve_apply_enabled():
        return {"queued": False, "reason": "disabled"}
    if not intake.bundle_id:
        return {"queued": False, "reason": "no_bundle"}
    from ..celery_tasks import enqueue_apply

    enqueue_apply(intake.bundle_id, dry_run=False, reconcile_after=True)
    logger.info(
        "migration_cloud.intake_pipeline: promotion apply enqueued intake_id=%s bundle_id=%s",
        intake.id, intake.bundle_id,
    )
    return {"queued": True, "bundle_id": intake.bundle_id}


def dry_run_preview(intake: MigrationIntakeRequest) -> Optional[dict[str, Any]]:
    """Return the bundle's dry-run preview totals for the review screen, or None."""
    if not intake.bundle_id or intake.bundle is None:
        return None
    preview = (intake.bundle.size_summary or {}).get("last_dry_run")
    return preview if isinstance(preview, dict) else None
