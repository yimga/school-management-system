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
from django.http import Http404
from django.shortcuts import redirect, render
from django.views import View

from . import defaults as mc_defaults
from .accelerators.runmycampus_canonical import (
    canonical_domain_choices,
    is_valid_canonical_domain,
)
from .models import IntakeMethod, MigrationBundle, SlaTier
from .reliability import idempotent_post, safe_500
from .services import BundleIngestionService, BundleSpec
from .views_connectors import _connector_reverse, _request_school

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
        bundle = MigrationBundle.objects.get(pk=bundle_id)
    except (MigrationBundle.DoesNotExist, ValueError, TypeError):
        raise Http404("bundle not found")
    if bundle.school_id != getattr(school, "pk", None):
        raise Http404("bundle not found")
    return bundle


def _idempotency_key(school_id, user_pk, digests) -> str:
    """Stable key so a double-submit of the same files collapses to one bundle."""
    signature = "|".join(sorted(digests)) if digests else secrets.token_urlsafe(16)
    composite = f"tenant-upload|{school_id or '-'}|{user_pk or '-'}|{signature}"
    return "mc-" + hashlib.sha256(composite.encode("utf-8")).hexdigest()[:48]


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


class TenantMigrationUploadView(LoginRequiredMixin, View):
    """GET → connectionless dropzone. POST → stage files, ingest, auto-advance."""

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
            schema_name=getattr(school, "schema_name", "") or "",
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
            f"Uploaded {result.artifacts_registered} file(s). We auto-detected the "
            "format and the kind of records in each — review below, then import.",
        )
        return redirect(_connector_reverse(request, "bundle-review", bundle_id=result.bundle_id))


class TenantMigrationReviewView(LoginRequiredMixin, View):
    """GET → per-file detected format + entity + confidence, with override.
    POST → save per-file entity overrides and re-detect."""

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
                }
            )
        return {
            "page_title": "Review & import",
            "bundle": bundle,
            "artifact_rows": rows,
            "domain_choices": canonical_domain_choices(),
            "apply_result": apply_result,
            "upload_url": _connector_reverse(request, "upload"),
            "review_url": _connector_reverse(request, "bundle-review", bundle_id=bundle.pk),
            "apply_url": _connector_reverse(request, "bundle-apply", bundle_id=bundle.pk),
            "home_url": _connector_reverse(request, "connector-home"),
        }


class TenantMigrationApplyView(LoginRequiredMixin, View):
    """POST → import the reviewed bundle into the caller's OWN school.

    Safety mirrors the operator apply: DRY-RUN by default; a live write requires
    an explicit ``confirm=1``. Tenant-scoped (a caller can only apply their own
    bundle). Renders the review page with the (dry-run or live) result totals.
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
            messages.success(
                request,
                f"Imported into your school: {result.total_created} created, "
                f"{result.total_updated} updated, {result.total_quarantined} held for review.",
            )
        context = TenantMigrationReviewView().build_context(request, bundle, apply_result=summary)
        return render(request, self.template_name, context)
