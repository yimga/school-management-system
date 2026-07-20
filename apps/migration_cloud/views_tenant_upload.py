"""Tenant connectionless file upload → auto-detect → review → import.

Gives the TENANT (on the ``/school/setup/migration-cloud/`` host) a direct,
connection-FREE door to the Universal Bundle pipeline that already powers the
operator wizard: drop an Excel / CSV / TSV / JSON / PDF / ZIP export and the
engine auto-detects the FORMAT (``profiler``) AND classifies the ENTITY per
file — students / staff / guardians / attendance / grades / … — via the domain
classifier (``classifiers/domain.py``), then the tenant reviews the detection
and imports into their OWN school.

Why a bespoke tenant surface (not the operator ``intake_new.html``): that
template hardcodes ``{% url 'migration_cloud_super:… %}`` / ``migration_cloud_portal``
names that ``NoReverseMatch`` (→ 500) on the tenant host. This surface instead
drives the same SERVICE layer (``BundleIngestionService`` → ``advance_bundle`` →
``apply_bundle``) and renders through the tenant connector wizard base
(``portal_base``); every URL is pre-resolved in the view via ``_connector_reverse``
so the templates carry no cross-host ``{% url %}`` reverses.

Security posture mirrors the sibling connector-import surface (``LoginRequiredMixin``
+ tenant scoping); the only DESTRUCTIVE step — a live apply — is dry-run by
default and requires an explicit ``confirm=1``. Cross-tenant access is a 404
(never 403), so id-enumeration cannot distinguish "exists elsewhere".
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views import View

from . import defaults as mc_defaults
from .schema_binding import resolve_school_schema_name
from .accelerators.runmycampus_canonical import (
    canonical_domain_choices,
    is_valid_canonical_domain,
)
from .models import BundleStatus, IntakeMethod, MigrationBundle, SlaTier

# Statuses where auto-detection (profile → classify → map) is still running, so
# the review page should show a live progress widget and keep polling.
_DETECTING_STATUSES = frozenset(
    {
        BundleStatus.PENDING,
        BundleStatus.INGESTING,
        BundleStatus.PROFILED,
        BundleStatus.CLASSIFIED,
    }
)
# Terminal-failure statuses — stop polling, tell the tenant what to try.
_FAILED_STATUSES = frozenset({BundleStatus.FAILED, BundleStatus.ABORTED})


def _is_detecting(bundle) -> bool:
    """True while the pipeline is still profiling/classifying/mapping the upload."""
    return bundle.status in _DETECTING_STATUSES
from .reliability import idempotent_post, safe_500
from .services import BundleIngestionService, BundleSpec
from .views_connectors import _connector_reverse, _request_school
from apps.accounts.decorators import user_is_tenant_admin

logger = logging.getLogger(__name__)

# Extensions the profiler can actually READ into rows today (see ``profiler.py``
# / the intake adapters). Advisory ``accept=`` hint only — the profiler
# re-sniffs every file by magic bytes, so a mis-named file is still classified.
_ACCEPTED_UPLOAD_EXTENSIONS = (
    ".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls",
    ".json", ".jsonl", ".ndjson", ".zip", ".pdf",
)


def _persist_uploads(files) -> tuple[list[str], list[str]]:
    """Stream uploads to durable MEDIA storage; return ``(paths, sha256s)``.

    Mirrors ``MigrationCloudIntakeView._persist_uploads`` so the tenant path
    stages files identically — under
    ``MEDIA_ROOT/migration_cloud/intake/YYYY-MM-DD/<slot>/`` — and survives a
    process restart before the profiler re-opens them. Single-pass hash.
    """
    media_root = Path(getattr(settings, "MEDIA_ROOT", "media"))
    slot = secrets.token_urlsafe(12).replace("/", "_").replace("=", "")
    dest_dir = media_root / "migration_cloud" / "intake" / date.today().isoformat() / slot
    dest_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[str] = []
    digests: list[str] = []
    for f in files:
        safe_name = Path(f.name).name or "upload.bin"
        target = dest_dir / safe_name
        digest = hashlib.sha256()
        with target.open("wb") as out:
            for chunk in f.chunks():
                out.write(chunk)
                digest.update(chunk)
        saved_paths.append(str(target))
        digests.append(digest.hexdigest())
    return saved_paths, digests


def _max_upload_bytes() -> int:
    try:
        return int(mc_defaults.get("migration_cloud.intake.max_artifact_bytes"))
    except Exception:  # noqa: BLE001 — defensive default
        return 1024 * 1024 * 1024  # 1 GiB  # magic-number-allow: byte-size-cap


def _tenant_bundle_or_404(request, bundle_id: int) -> MigrationBundle:
    """Resolve a bundle scoped to the caller's active tenant school (IDOR guard).

    A cross-tenant / unknown id is a 404 (never 403) so id-enumeration cannot
    distinguish "exists elsewhere" from "doesn't exist" — same contract as the
    operator ``_tenant_scoped_bundle`` helper.
    """
    school = _request_school(request)
    if school is None:
        raise Http404()
    try:
        # Scoped by construction rather than fetch-then-compare: the school is in
        # the WHERE clause, so the isolation cannot be lost by deleting a check
        # below it. Identical contract — a cross-tenant id simply does not match
        # and raises DoesNotExist, which is the same 404 as an unknown id.
        bundle = MigrationBundle.objects.get(pk=bundle_id, school=school)
    except (MigrationBundle.DoesNotExist, ValueError, TypeError):
        raise Http404("bundle not found")
    return bundle


def _idempotency_key(school_id, user_pk, digests) -> str:
    """Stable key so a double-submit of the same files collapses to one bundle."""
    signature = "|".join(sorted(digests)) if digests else secrets.token_urlsafe(16)
    composite = f"tenant-upload|{school_id or '-'}|{user_pk or '-'}|{signature}"
    return "mc-" + hashlib.sha256(composite.encode("utf-8")).hexdigest()[:48]


def _row_hint(artifact) -> str:
    """Plain-language explanation when a file profiled to zero rows or is quarantined."""
    if artifact.quarantined:
        reason = (artifact.quarantine_reason or "").strip()
        if reason:
            return reason
        return (
            "This file was held for review and will not import until the issue "
            "is fixed. Re-export a clean CSV/Excel from your old system, or "
            "correct the record type below and re-detect."
        )
    if (artifact.row_count or 0) > 0:
        return ""
    fmt = artifact.detected_format
    if fmt == "pdf":
        return (
            "No text could be read from this PDF. Digitally-generated PDFs "
            "(exported from another system) import automatically — but a "
            "scanned or photographed PDF has no text layer. Re-export it as "
            "CSV or Excel from your old system, or ask us to enable OCR."
        )
    if fmt in ("xlsx", "xls"):
        return (
            "No rows were found on the first worksheet. Make sure the first "
            "sheet has a header row followed by data, or save it as CSV and "
            "upload again."
        )
    if fmt in ("csv", "tsv", "json"):
        return (
            "No data rows were found. Confirm the file has a header row and at "
            "least one data row, then upload again."
        )
    if fmt in ("zip", "archive"):
        return (
            "No importable members were found in this archive. Include CSV, "
            "Excel, JSON, or PDF exports inside the ZIP and try again."
        )
    return (
        "No rows were detected in this file. Re-export as CSV or Excel from "
        "your old system and upload again."
    )

def _advance(bundle_id) -> None:
    """Run profile → classify → map after intake. Celery if up, inline otherwise
    so a broker outage never blocks the tenant's migration."""
    try:
        from .celery_tasks import enqueue_advance

        if enqueue_advance(bundle_id, use_accelerator=True) is not None:
            return
    except Exception:  # noqa: BLE001 — fall through to inline
        logger.warning("mc tenant upload: enqueue_advance failed for %s; inline", bundle_id)
    try:
        from .pipeline import advance_bundle

        advance_bundle(bundle_id=bundle_id, use_accelerator=True)
    except Exception:  # noqa: BLE001 — surfaced on the review page instead
        logger.exception("mc tenant upload: inline advance failed for %s", bundle_id)


def _sync_tenant_domain_overrides(bundle) -> None:
    """Push per-file tenant corrections into the pipeline override map and remount.

    Tenant review writes ``artifact.assigned_domain``, but ``advance_bundle`` only
    honors ``discovery_summary.operator_assigned_domains``, and is a no-op once
    status is already ``MAPPED``. Sync the map and rewind to ``PROFILED`` so
    classify + map re-run with the tenant's tags (P1-Override).
    """
    summary = dict(bundle.discovery_summary or {})
    operator = dict(summary.get("operator_assigned_domains") or {})
    for artifact in bundle.artifacts.all():
        tag = (artifact.assigned_domain or "").strip()
        path_key = artifact.path_within_bundle or ""
        name_key = artifact.filename or ""
        if tag and is_valid_canonical_domain(tag):
            if path_key:
                operator[path_key] = tag
            if name_key:
                operator[name_key] = tag
        else:
            if path_key:
                operator.pop(path_key, None)
            if name_key:
                operator.pop(name_key, None)
    summary["operator_assigned_domains"] = operator
    bundle.discovery_summary = summary
    update_fields = ["discovery_summary", "updated_at"]
    if bundle.status in (
        BundleStatus.CLASSIFIED,
        BundleStatus.MAPPED,
        BundleStatus.READY,
    ):
        # Rewind so Phase U3/U4 run again with operator tags.
        bundle.status = BundleStatus.PROFILED
        update_fields.append("status")
    bundle.save(update_fields=update_fields)


def _progress_payload(bundle) -> dict:
    """Live auto-detection progress for the review-page poller.

    Recomputes the per-stage snapshot from the bundle's current status + event
    stream (same helper the operator DAG view uses) and adds the plain flags the
    tenant widget needs: ``detecting`` (still working), ``done`` (detection
    finished — reload to reveal the review table), ``failed`` (stop + advise).
    Best-effort: a snapshot failure degrades to the last saved snapshot rather
    than 500-ing the poller.
    """
    try:
        from .progress import refresh_snapshot

        snapshot = refresh_snapshot(bundle=bundle)
    except Exception:  # noqa: BLE001 — never break the poller on a snapshot error
        logger.debug("tenant progress: snapshot failed for %s", bundle.pk, exc_info=True)
        snapshot = getattr(bundle, "progress_snapshot", None) or {}

    detecting = _is_detecting(bundle)
    detected = []
    for art in bundle.artifacts.all():
        candidates = art.inferred_domain if isinstance(art.inferred_domain, list) else []
        top = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        if top.get("domain"):
            detected.append({"filename": art.filename, "domain": top.get("domain")})
    return {
        "bundle_id": bundle.pk,
        "status": bundle.status,
        "status_label": bundle.get_status_display(),
        "detecting": detecting,
        "done": not detecting and bundle.status not in _FAILED_STATUSES,
        "failed": bundle.status in _FAILED_STATUSES,
        "advance_error": (bundle.size_summary or {}).get("error") or "",
        "snapshot": snapshot,
        "detected": detected,
    }


class _TenantAdminWriteRequiredMixin(LoginRequiredMixin):
    """Gate a Migration Cloud tenant WRITE surface on the tenant-admin tier.

    ``LoginRequiredMixin`` alone answers only "authenticated"; combined with
    ``_request_school`` (which falls back to the caller's FIRST school membership
    with no role filter) the effective gate was "authenticated + ANY membership".
    Because SAML/SCIM provisions a membership for EVERY IdP user, that let a
    teacher / parent / student — anyone with a login — POST ``confirm=1`` and have
    ``apply_bundle`` irreversibly overwrite the school's live data across the
    landable domains (only students + grades have rollback handlers).

    This mixin additionally requires the caller be the tenant-admin tier for the
    SAME school the write targets — owner / ``role=ADMIN`` / ``settings.manage``,
    plus the audited superuser break-glass — via the canonical
    :func:`apps.accounts.decorators.user_is_tenant_admin`. The school is resolved
    with ``_request_school``, exactly as :func:`_tenant_bundle_or_404` resolves the
    bundle's school, so the authorization decision and the write are bound to one
    school and cannot drift apart. The cross-tenant IDOR guard
    (``_tenant_bundle_or_404`` — school in the WHERE clause) is untouched; this adds
    the intra-tenant privilege check it never had.

    Denial semantics match ``tenant_admin_required``: an authenticated non-admin
    gets ``PermissionDenied`` (rendered by the tenant ``handler403`` branded 403),
    while an unauthenticated caller is bounced to login by ``LoginRequiredMixin``.
    """

    def dispatch(self, request, *args, **kwargs):
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False) and not user_is_tenant_admin(
            user, _request_school(request)
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class TenantMigrationProgressView(LoginRequiredMixin, View):
    """GET JSON: live auto-detection progress for the caller's OWN bundle.

    Polled by ``bundle_review.html`` while profile → classify → map runs (async
    on the Celery worker in production, or already-complete inline on a broker
    outage). Tenant-scoped via :func:`_tenant_bundle_or_404` — a cross-tenant or
    unknown id is a 404 (never 403), so id-enumeration can't distinguish "exists
    elsewhere". Read-only from the tenant's perspective; grants no operator
    visibility (isolation preserved).
    """

    def get(self, request, bundle_id: int):
        bundle = _tenant_bundle_or_404(request, bundle_id)
        return JsonResponse(_progress_payload(bundle))


class TenantMigrationUploadView(_TenantAdminWriteRequiredMixin, View):
    """GET → connectionless dropzone. POST → stage files, ingest, auto-advance.

    Tenant-admin gated (write surface): staging + auto-advance mutate the school's
    migration state, so a non-admin member is refused (403). See
    :class:`_TenantAdminWriteRequiredMixin`.
    """

    template_name = "migration_cloud/connector/upload.html"

    def _base_context(self, request, school):
        return {
            "page_title": "Upload & auto-import",
            "school": school,
            "accepted_extensions": ", ".join(_ACCEPTED_UPLOAD_EXTENSIONS),
            "domain_choices": canonical_domain_choices(),
            "cancel_url": _connector_reverse(request, "connector-home"),
        }

    def get(self, request):
        school = _request_school(request)
        if school is None:
            raise Http404()
        return render(request, self.template_name, self._base_context(request, school))

    @idempotent_post
    @safe_500
    def post(self, request):
        school = _request_school(request)
        if school is None:
            raise Http404()

        files = [f for f in request.FILES.getlist("artifacts") if f and f.size > 0]
        errors: list[str] = []
        if not files:
            errors.append("Attach at least one non-empty file to upload.")
        else:
            cap = _max_upload_bytes()
            oversized = [f.name for f in files if f.size > cap]
            if oversized:
                errors.append(
                    f"File(s) exceed the {cap:,}-byte cap: {', '.join(oversized)}."
                )
        if errors:
            for msg in errors:
                messages.error(request, msg)
            ctx = self._base_context(request, school)
            return render(request, self.template_name, ctx, status=400)

        saved_paths, digests = _persist_uploads(files)
        handle = saved_paths[0] if len(saved_paths) == 1 else saved_paths
        spec = BundleSpec(
            intake_method=IntakeMethod.FILE_UPLOAD,
            handle=handle,
            school_id=school.pk,
            schema_name=resolve_school_schema_name(school),
            label=(request.POST.get("label") or "").strip() or f"Upload — {len(files)} file(s)",
            source_hint=(request.POST.get("source_hint") or "").strip(),
            sla_tier=SlaTier.SMALL,
            idempotency_key=_idempotency_key(school.pk, getattr(request.user, "pk", None), digests),
            intake_source_uri=(
                saved_paths[0] if len(saved_paths) == 1 else f"{len(saved_paths)} files staged"
            ),
            triggered_by_id=getattr(request.user, "pk", None),
        )
        try:
            result = BundleIngestionService().ingest(spec)
        except Exception as exc:  # noqa: BLE001 — surface intake failure inline
            logger.exception("mc tenant upload: intake failed")
            messages.error(request, f"We couldn't read that upload: {type(exc).__name__}.")
            return redirect(_connector_reverse(request, "upload"))

        _advance(result.bundle_id)
        messages.success(
            request,
            f"Uploaded {result.artifacts_registered} file(s). Detection is running — "
            "review the results next. Nothing is in your school until you click "
            "“Import into my school.”",
        )
        return redirect(_connector_reverse(request, "bundle-review", bundle_id=result.bundle_id))


class TenantMigrationReviewView(_TenantAdminWriteRequiredMixin, View):
    """GET → per-file detected format + entity + confidence, with override.
    POST → save per-file entity overrides and re-detect.

    Tenant-admin gated (write surface): the POST persists domain overrides and
    re-runs the detection pipeline, and the GET renders the "Import into my school"
    control — the whole review/import step is an admin workflow. See
    :class:`_TenantAdminWriteRequiredMixin`."""

    template_name = "migration_cloud/connector/bundle_review.html"

    def get(self, request, bundle_id: int):
        bundle = _tenant_bundle_or_404(request, bundle_id)
        return render(request, self.template_name, self.build_context(request, bundle))

    @idempotent_post
    @safe_500
    def post(self, request, bundle_id: int):
        bundle = _tenant_bundle_or_404(request, bundle_id)
        changed = 0
        for artifact in bundle.artifacts.all():
            field = f"assigned_domain_{artifact.pk}"
            if field not in request.POST:
                continue
            value = (request.POST.get(field) or "").strip()
            if value and value != "auto" and is_valid_canonical_domain(value):
                if artifact.assigned_domain != value:
                    artifact.assigned_domain = value
                    artifact.save(update_fields=["assigned_domain", "updated_at"])
                    changed += 1
            elif value in ("", "auto") and artifact.assigned_domain:
                artifact.assigned_domain = ""
                artifact.save(update_fields=["assigned_domain", "updated_at"])
                changed += 1
        if changed:
            _sync_tenant_domain_overrides(bundle)
            _advance(bundle.pk)
            messages.success(request, f"Updated {changed} file(s) and re-detected.")
        else:
            messages.info(request, "No changes to apply.")
        return redirect(_connector_reverse(request, "bundle-review", bundle_id=bundle.pk))

    def build_context(self, request, bundle, apply_result=None):
        rows = []
        for artifact in bundle.artifacts.all():
            candidates = artifact.inferred_domain if isinstance(artifact.inferred_domain, list) else []
            top = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
            detected = (artifact.assigned_domain or top.get("domain", "") or "").strip()
            rows.append(
                {
                    "id": artifact.pk,
                    "filename": artifact.filename,
                    "format": artifact.get_detected_format_display(),
                    "rows": artifact.row_count,
                    "columns": artifact.column_count,
                    "assigned": artifact.assigned_domain,
                    "detected_domain": top.get("domain", ""),
                    "confidence_pct": (
                        round(float(top.get("confidence")) * 100)
                        if top.get("confidence") is not None
                        else None
                    ),
                    "source": artifact.inferred_source,
                    "quarantined": artifact.quarantined,
                    "quarantine_reason": artifact.quarantine_reason,
                    "hint": _row_hint(artifact),
                    "dfv_only": detected in ("payroll", "compliance"),
                }
            )
        return {
            "page_title": "Review & import",
            "bundle": bundle,
            "artifact_rows": rows,
            "domain_choices": canonical_domain_choices(),
            "apply_result": apply_result,
            "verification": _build_verification(bundle),
            "repair": _build_repair(bundle),
            "repair_url": _connector_reverse(request, "bundle-repair", bundle_id=bundle.pk),
            "retry_url": _connector_reverse(request, "bundle-retry", bundle_id=bundle.pk),
            "advance_error": (bundle.size_summary or {}).get("error") or "",
            "detection_failed": bundle.status in _FAILED_STATUSES,
            "detecting": _is_detecting(bundle),
            "progress_url": _connector_reverse(request, "bundle-progress", bundle_id=bundle.pk),
            "upload_url": _connector_reverse(request, "upload"),
            "review_url": _connector_reverse(request, "bundle-review", bundle_id=bundle.pk),
            "apply_url": _connector_reverse(request, "bundle-apply", bundle_id=bundle.pk),
            "home_url": _connector_reverse(request, "connector-home"),
        }


def _safe_reconcile(bundle) -> None:
    """Run the post-apply reconciliation + tenant-visibility verification pass.

    Best-effort: writes ``bundle.reconciliation_summary`` (source -> landed ->
    visible per domain) so the results page can prove the data actually populated
    the school. A reconcile failure must never break the import the tenant ran.
    """
    try:
        from .reconciliation import reconcile_bundle

        reconcile_bundle(bundle_id=bundle.pk)
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning(
            "tenant apply: post-apply reconcile failed for bundle %s",
            bundle.pk,
            exc_info=True,
        )


def _build_verification(bundle):
    """Compact per-domain "did it land + is it visible in the school" rows.

    Reads the reconciliation summary written by :func:`_safe_reconcile`. Returns
    ``None`` when no verification has run yet (the pre-import review GET or a
    dry-run), so the template simply omits the section.
    """
    summary = getattr(bundle, "reconciliation_summary", None) or {}
    per_domain = summary.get("per_domain") or []
    if not per_domain:
        return None
    rows = []
    ok = True
    for d in per_domain:
        visible = d.get("target_visible_count")
        created = d.get("target_created") or 0
        landed = created + (d.get("target_updated") or 0)
        drift = visible is not None and created > 0 and visible < created
        if drift:
            ok = False
        rows.append(
            {
                "domain": d.get("domain"),
                "source": d.get("source_count"),
                "landed": landed,
                "visible_label": "—" if visible is None else visible,
                "drift": drift,
            }
        )
    return {"rows": rows, "ok": ok, "notes": summary.get("notes") or []}


# Blockers worth surfacing to the tenant even when repair is withheld — a real,
# actionable safety hold (vs. a benign "not applied yet / already clean" state,
# for which the repair panel simply stays hidden on the normal review flow).
_ACTIONABLE_REPAIR_BLOCKERS = frozenset({"financial_guardrail_failed", "finance_requires_atomic"})


def _build_repair(bundle):
    """Compact repair affordance for the review page.

    Returns ``{repairable, reason, blockers, issue_count}`` from
    :func:`repair.repair_readiness` so the template can show a "Repair this
    import" button — or, when a real safety hold applies, a plain explanation.
    Returns ``None`` (panel hidden) for benign non-repairable states (a fresh
    upload not yet imported, an already-clean apply), so the panel only appears
    when there is something to act on. Cheap read-only; never raises.
    """
    try:
        from .repair import repair_readiness

        r = repair_readiness(bundle)
        if not r.repairable and not (_ACTIONABLE_REPAIR_BLOCKERS & set(r.blockers)):
            return None
        return {
            "repairable": r.repairable,
            "reason": r.reason,
            "blockers": r.blockers,
            "issue_count": r.issue_count,
        }
    except Exception:  # noqa: BLE001 — a readiness hiccup must never break the page
        logger.debug("tenant repair: readiness failed for %s", bundle.pk, exc_info=True)
        return None


class TenantMigrationApplyView(_TenantAdminWriteRequiredMixin, View):
    """POST → import the reviewed bundle into the caller's OWN school.

    Safety mirrors the operator apply: DRY-RUN by default; a live write requires
    an explicit ``confirm=1``. Tenant-scoped (a caller can only apply their own
    bundle) AND tenant-admin gated — a non-admin member is refused (403) before
    ``apply_bundle`` runs, closing the "any member can overwrite the school's live
    data" hole. Renders the review page with the (dry-run or live) result totals.
    See :class:`_TenantAdminWriteRequiredMixin`.
    """

    template_name = "migration_cloud/connector/bundle_review.html"

    @idempotent_post
    @safe_500
    def post(self, request, bundle_id: int):
        from .orchestrator import apply_bundle

        bundle = _tenant_bundle_or_404(request, bundle_id)
        confirmed = str(request.POST.get("confirm", "")).lower() in ("1", "true", "yes", "on")
        dry_run = not confirmed
        try:
            result = apply_bundle(bundle_id=bundle.pk, dry_run=dry_run)
        except ValueError as exc:
            messages.error(
                request,
                f"This upload isn't ready to import yet ({exc}). Give auto-detect a "
                "moment, refresh, then try again.",
            )
            return redirect(_connector_reverse(request, "bundle-review", bundle_id=bundle.pk))

        summary = {
            "dry_run": result.dry_run,
            "status": result.status,
            "created": result.total_created,
            "updated": result.total_updated,
            "quarantined": result.total_quarantined,
            "per_artifact": [
                {
                    "domain": item.domain,
                    "status": item.status,
                    "created": item.result.created,
                    "updated": item.result.updated,
                    "quarantined": item.result.quarantined,
                }
                for item in result.per_artifact
            ],
        }
        if result.dry_run:
            messages.info(
                request,
                "Preview only — nothing was written. Check the numbers below, then "
                "choose “Import into my school” to make it real.",
            )
        else:
            # Post-apply: re-query the tenant to prove the rows actually landed
            # and are visible in the school, then refresh so build_context reads
            # the fresh reconciliation summary.
            _safe_reconcile(bundle)
            bundle.refresh_from_db()
            messages.success(
                request,
                f"Imported into your school: {result.total_created} created, "
                f"{result.total_updated} updated, {result.total_quarantined} held for review.",
            )
        context = TenantMigrationReviewView().build_context(request, bundle, apply_result=summary)
        return render(request, self.template_name, context)


class TenantMigrationRetryAdvanceView(_TenantAdminWriteRequiredMixin, View):
    """POST → re-run detection (advance) for a stuck or failed upload.

    Rewinds FAILED/ABORTED bundles to INGESTING so ``advance_bundle`` can
    profile/classify/map again. Tenant-admin gated; tenant-scoped.
    """

    @idempotent_post
    @safe_500
    def post(self, request, bundle_id: int):
        bundle = _tenant_bundle_or_404(request, bundle_id)
        if bundle.status in _FAILED_STATUSES:
            summary = dict(bundle.size_summary or {})
            summary.pop("error", None)
            bundle.size_summary = summary
            bundle.status = BundleStatus.INGESTING
            bundle.save(update_fields=["status", "size_summary", "updated_at"])
        elif bundle.status in (
            BundleStatus.MAPPED,
            BundleStatus.READY,
            BundleStatus.CLASSIFIED,
        ):
            # Allow remount when detection looked done but tenant wants a re-run.
            bundle.status = BundleStatus.PROFILED
            bundle.save(update_fields=["status", "updated_at"])
        _advance(bundle.pk)
        messages.info(
            request,
            "Re-running detection. This page will update when files are ready to review.",
        )
        return redirect(_connector_reverse(request, "bundle-review", bundle_id=bundle.pk))


class TenantMigrationRepairView(_TenantAdminWriteRequiredMixin, View):
    """POST → safe, idempotent re-import (repair) of the caller's OWN bundle.

    Tenant-admin gated (write surface): a repair re-applies the bundle into the
    school, so a non-admin member is refused (403). See
    :class:`_TenantAdminWriteRequiredMixin`.

    For a bundle whose apply failed part-way or left rows held for review, this
    re-applies idempotently (upsert — no duplicates) and re-verifies. All the
    safety judgement lives in :func:`repair.repair_bundle` / ``repair_readiness``
    (refuses financial-guardrail failures, non-atomic finance, reconciled /
    in-flight / not-yet-applied bundles). Tenant-scoped (cross-tenant id → 404);
    ``@idempotent_post`` collapses an accidental double-click into one repair.
    """

    template_name = "migration_cloud/connector/bundle_review.html"

    @idempotent_post
    @safe_500
    def post(self, request, bundle_id: int):
        from .repair import repair_bundle

        bundle = _tenant_bundle_or_404(request, bundle_id)
        result = repair_bundle(bundle_id=bundle.pk)
        bundle.refresh_from_db()

        if not result.ran:
            messages.info(request, result.message)
        elif result.ok:
            messages.success(request, result.message)
        else:
            messages.error(request, result.message)

        # Only surface the results/verification banner when the repair actually
        # re-imported cleanly; otherwise the message above carries the reason and
        # the review page renders normally (still offering repair if applicable).
        apply_result = None
        if result.ran and result.ok:
            apply_result = {
                "dry_run": False,
                "is_repair": True,
                "status": result.after_status,
                "created": result.created,
                "updated": result.updated,
                "quarantined": result.quarantined,
                "per_artifact": [],
            }
        context = TenantMigrationReviewView().build_context(
            request, bundle, apply_result=apply_result
        )
        return render(request, self.template_name, context)
