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
from django.utils import timezone
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


def _canonical_template_urls(request) -> dict[str, str]:
    """Resolve the canonical-template picker + zip URLs for the current host.

    The template routes live under the portal/super namespaces (not the connector
    wizard's), so we resolve defensively across the namespaces a given host may
    expose and fall through to empty strings — the upload template only shows the
    "use our templates" panel when a URL is present, so a host without the routes
    simply omits it (never a NoReverseMatch 500). This surfaces the ready-made
    import templates to self-serve tenants, who previously could only reach them
    from the operator intake page.
    """
    from django.urls import NoReverseMatch, reverse

    out: dict[str, str] = {"template_picker_url": "", "template_zip_url": ""}
    resolvers = (
        ("template_picker_url", "canonical_template_picker"),
        ("template_zip_url", "canonical_template_zip"),
    )
    for key, name in resolvers:
        for namespace in (
            "migration_cloud_portal",
            "migration_cloud_super",
            "migration_cloud_connector",
        ):
            try:
                out[key] = reverse(f"{namespace}:{name}")
                break
            except NoReverseMatch:
                continue
    return out


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
    """Run profile → classify → map after intake — always off the HTTP thread."""
    try:
        from .celery_tasks import enqueue_advance

        if enqueue_advance(bundle_id, use_accelerator=True) is not None:
            return
    except Exception:  # noqa: BLE001 — fall through to background kick
        logger.warning(
            "mc tenant upload: enqueue_advance failed for %s; background kick",
            bundle_id,
            exc_info=True,
        )
    try:
        from .celery_tasks import _kick_advance_off_request

        _kick_advance_off_request(bundle_id, use_accelerator=True)
    except Exception:  # noqa: BLE001 — surfaced on the review page instead
        logger.exception(
            "mc tenant upload: background advance kick failed for %s", bundle_id
        )


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


# Seconds a still-PENDING apply-outbox row may sit before the review page tells
# the tenant honestly that the background importer hasn't picked it up yet
# (worker idle / broker backlog) — instead of a spinner that never resolves.
_IMPORT_QUEUE_STUCK_SECONDS = 90  # magic-number-allow: import-queue-stuck-threshold-seconds


def _import_flight(bundle) -> dict:
    """Whether a live import / repair is queued or running for this bundle.

    The durable apply row on the HeavyWorkOutbox is the authoritative signal: it
    exists (PENDING → PROCESSING) for the whole life of the background apply the
    tenant just kicked, so the review page can show a real "importing…" state and
    poll until it settles — instead of reverting to a bare "ready to import" look
    that makes a working repair appear to do nothing. ``APPLYING`` on the bundle
    itself (or a PROCESSING row) refines the label to "running". A PENDING row
    older than :data:`_IMPORT_QUEUE_STUCK_SECONDS` means no worker has drained it
    yet, which is surfaced honestly rather than spun on forever.

    Read-only + best-effort: an outbox lookup failure degrades to "not in flight"
    (the pre-existing behaviour) rather than breaking the review page.
    """
    running = getattr(bundle, "status", "") == BundleStatus.APPLYING
    row = None
    try:
        from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

        row = (
            # tenant-isolation-allow: HeavyWorkOutbox is a public-schema orchestration
            # table; bundle_id is the globally-unique shared MigrationBundle pk and the
            # bundle is tenant-resolved via _tenant_bundle_or_404(school=), so this
            # filter transitively pins to one school. (MC_APPLY_BUNDLE outbox rows do
            # not carry school_id, so a school_id= filter would match nothing.)
            HeavyWorkOutbox.objects.filter(
                bundle_id=bundle.pk,
                kind=HeavyWorkOutbox.Kind.MC_APPLY_BUNDLE,
                status__in=(
                    HeavyWorkOutbox.Status.PENDING,
                    HeavyWorkOutbox.Status.PROCESSING,
                ),
            )
            .order_by("-created_at")
            .first()
        )
    except Exception:  # noqa: BLE001 — never break the review page on an outbox read
        logger.debug(
            "tenant import-flight: outbox read failed for %s",
            getattr(bundle, "pk", "?"),
            exc_info=True,
        )
        row = None

    if not running and row is None:
        return {"in_flight": False, "phase": "", "stuck": False, "dry_run": False}

    processing = row is not None and row.status == HeavyWorkOutbox.Status.PROCESSING
    pending = row is not None and row.status == HeavyWorkOutbox.Status.PENDING
    dry_run = (
        bool((getattr(row, "payload", None) or {}).get("dry_run")) if row is not None else False
    )
    stuck = False
    if pending and not running:
        try:
            stuck = (
                timezone.now() - row.created_at
            ).total_seconds() > _IMPORT_QUEUE_STUCK_SECONDS
        except Exception:  # noqa: BLE001 — a clock/None hiccup must not stick the page
            stuck = False
    elif running or processing:
        # A CLAIMED apply that stopped heartbeating is wedged, not working. Checking
        # only the PENDING branch above made this page spin forever on the single
        # commonest failure -- a worker killed mid-apply (deploy, OOM, connection
        # exhaustion) -- because that leaves the bundle at APPLYING (running=True) or
        # the row at PROCESSING, and neither is `pending`, so `stuck` stayed False and
        # the tenant saw "Working..." indefinitely. The orchestrator heartbeats the
        # bundle at every wave/artifact, so a stale heartbeat is the honest signal;
        # repair.applying_stale_by_time is the project's single source of truth for it.
        try:
            from .repair import applying_stale_by_time

            stuck = applying_stale_by_time(bundle)
        except Exception:  # noqa: BLE001 — never break the review page on this probe
            stuck = False
    return {
        "in_flight": True,
        "phase": "running" if (running or processing) else "queued",
        "stuck": stuck,
        "dry_run": dry_run,
    }


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

        # persist=False: this is a hot read-only poller (~2.5 s/viewer); compute
        # the live snapshot without a DB write on a GET. The worker keeps the
        # stored copy fresh at each stage boundary.
        snapshot = refresh_snapshot(bundle=bundle, persist=False)
    except Exception:  # noqa: BLE001 — never break the poller on a snapshot error
        logger.debug("tenant progress: snapshot failed for %s", bundle.pk, exc_info=True)
        snapshot = getattr(bundle, "progress_snapshot", None) or {}

    detecting = _is_detecting(bundle)
    flight = _import_flight(bundle)
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
        # An in-flight import/repair must keep the poller watching (not "done") so
        # the review page reloads to reveal the result once the apply settles.
        "importing": flight["in_flight"],
        "import_phase": flight["phase"],
        "import_stuck": flight["stuck"],
        "done": (
            not detecting
            and not flight["in_flight"]
            and bundle.status not in _FAILED_STATUSES
        ),
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

    Polled by ``bundle_review.html`` while profile → classify → map runs on the
    background worker (a durable ``HeavyWorkOutbox`` row drained off the HTTP
    thread; on a broker/worker outage the row simply waits, so the poller keeps
    watching rather than seeing a synchronous result). Tenant-scoped via
    :func:`_tenant_bundle_or_404` — a cross-tenant or unknown id is a 404 (never
    403), so id-enumeration can't distinguish "exists elsewhere". Read-only: the
    snapshot is computed with ``persist=False`` (no DB write on GET) and grants no
    operator visibility (isolation preserved).
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
        ctx = {
            "page_title": "Upload & auto-import",
            "school": school,
            "accepted_extensions": ", ".join(_ACCEPTED_UPLOAD_EXTENSIONS),
            "domain_choices": canonical_domain_choices(),
            "cancel_url": _connector_reverse(request, "connector-home"),
        }
        ctx.update(_canonical_template_urls(request))
        return ctx

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

        # upload-validation-allow: schema-agnostic SIS export (CSV/TSV/TXT/JSON/JSONL/XLS/XLSX/ZIP/PDF) has no single magic-byte type — re-sniffed + structure-validated by the profiler at parse time; streaming byte-size cap enforced below; a full-buffer AV read would defeat the GB-scale streaming-to-disk design
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


def _field_choices_for_domain(domain: str) -> list[str]:
    """Canonical field names a source column may map to, for one domain's <select>.

    Reuses the ontology (the mapper's own source of truth); an unknown/absent
    domain (e.g. a header-only domain not in ``CANONICAL_ONTOLOGY``) yields an
    empty list — the review select then only offers the current mapping + the
    "keep as custom field" escape, which is honest rather than misleading.
    """
    if not domain:
        return []
    try:
        from .ontology import iter_canonical_fields

        return sorted({f["canonical_field"] for f in iter_canonical_fields(domain)})
    except Exception:  # noqa: BLE001 — a catalog hiccup must never break the review page
        return []


def _column_mapping_rows(artifact_maps) -> list[dict]:
    """Shape the persisted per-artifact column→canonical mapping for the review UI.

    Reads the exact JSON the operator page reads and the orchestrator applies
    (``bundle.mapping_summary['per_artifact'][path]``). A column with no
    confident mapping is quarantined as ``custom_fields.<slug>`` by the mapper
    (never dropped); we surface that as an explicit "kept as custom field" state
    so a tenant admin understands nothing was lost.
    """
    out = []
    for m in artifact_maps or []:
        if not isinstance(m, dict):
            continue
        canon = str(m.get("canonical_field") or "")
        conf = m.get("confidence")
        out.append(
            {
                "source_column": m.get("source_column", ""),
                "canonical_field": canon,
                "confidence_pct": (
                    round(float(conf) * 100) if conf is not None else None
                ),
                "method": m.get("method", ""),
                "reasoning": m.get("reasoning", ""),
                "is_custom": canon.startswith("custom_fields."),
            }
        )
    return out


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
            # A record-type change re-runs classify+map, which would discard any
            # column edits submitted alongside it — so re-detect wins and column
            # overrides are intentionally not applied in the same pass.
            _sync_tenant_domain_overrides(bundle)
            _advance(bundle.pk)
            messages.success(request, f"Updated {changed} file(s) and re-detected.")
            return redirect(_connector_reverse(request, "bundle-review", bundle_id=bundle.pk))

        # No record-type change → apply any per-column mapping corrections in
        # place. This rewrites the SAME mapping_summary the apply reads; it does
        # NOT rewind/re-map (that would throw the tenant's choices away).
        mapping_changed = self._apply_column_overrides(request, bundle)
        if mapping_changed:
            messages.success(
                request,
                f"Updated {mapping_changed} column mapping(s). Re-run the import "
                "for the changes to take effect.",
            )
        else:
            messages.info(request, "No changes to apply.")
        return redirect(_connector_reverse(request, "bundle-review", bundle_id=bundle.pk))

    def _apply_column_overrides(self, request, bundle) -> int:
        """Rewrite ``mapping_summary['per_artifact']`` from the review form's selects.

        Fields are ``map__<artifact_pk>__<i>`` (chosen canonical field) with a
        companion ``mapsrc__<artifact_pk>__<i>`` (the source column). The override
        is matched to the stored mapping by source column (robust to reordering),
        mirroring the operator ``manual_correction`` recipe so a tenant override
        reaches landed data exactly as an operator's does. Returns the count of
        mappings actually changed.
        """
        per_artifact = (bundle.mapping_summary or {}).get("per_artifact") or {}
        if not per_artifact:
            return 0
        changed = 0
        for artifact in bundle.artifacts.all():
            path = artifact.path_within_bundle or ""
            mappings = per_artifact.get(path) or []
            if not mappings:
                continue
            for i in range(len(mappings)):
                sel_key = f"map__{artifact.pk}__{i}"
                if sel_key not in request.POST:
                    continue
                new_canon = (request.POST.get(sel_key) or "").strip()
                src_col = (request.POST.get(f"mapsrc__{artifact.pk}__{i}") or "").strip()
                if not new_canon or not src_col:
                    continue
                for m in mappings:
                    if (
                        isinstance(m, dict)
                        and str(m.get("source_column") or "") == src_col
                        and str(m.get("canonical_field") or "") != new_canon
                    ):
                        m["canonical_field"] = new_canon
                        m["confidence"] = max(float(m.get("confidence") or 0.0), 0.95)
                        m["method"] = "tenant_override"
                        m["reasoning"] = "Tenant correction via the mapping review."
                        changed += 1
            per_artifact[path] = mappings
        if changed:
            bundle.mapping_summary = {
                **(bundle.mapping_summary or {}),
                "per_artifact": per_artifact,
            }
            bundle.save(update_fields=["mapping_summary", "updated_at"])
        return changed

    def build_context(self, request, bundle, apply_result=None):
        rows = []
        # The auto-mapping the pipeline already computed + persisted — the same
        # JSON the operator page reads and the orchestrator applies. Surfacing it
        # here lets a tenant admin review + correct a wrong column mapping before
        # import, instead of the auto-map being silent.
        per_artifact = (bundle.mapping_summary or {}).get("per_artifact") or {}
        for artifact in bundle.artifacts.all():
            candidates = artifact.inferred_domain if isinstance(artifact.inferred_domain, list) else []
            top = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
            detected = (artifact.assigned_domain or top.get("domain", "") or "").strip()
            artifact_maps = per_artifact.get(artifact.path_within_bundle or "") or []
            mapping_rows = _column_mapping_rows(artifact_maps)
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
                    "mappings": mapping_rows,
                    "field_choices": _field_choices_for_domain(detected),
                }
            )
        flight = _import_flight(bundle)
        return {
            "page_title": "Review & import",
            "bundle": bundle,
            "artifact_rows": rows,
            "domain_choices": canonical_domain_choices(),
            "apply_result": apply_result,
            "verification": _build_verification(bundle),
            # Live import/repair state: the review page shows a polling progress
            # card and hides the write affordances while an apply is in flight,
            # then reveals the outcome (last_import) once it settles.
            "importing": flight["in_flight"],
            "import_flight": flight,
            "last_import": _last_import_summary(bundle),
            "repair": _build_repair(bundle),
            "repair_url": _connector_reverse(request, "bundle-repair", bundle_id=bundle.pk),
            "rollback": _build_rollback(bundle),
            "rollback_url": _connector_reverse(request, "bundle-rollback", bundle_id=bundle.pk),
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


def _last_import_summary(bundle):
    """Totals from the most recent LIVE apply, for the review GET.

    So a tenant who ran an import / repair sees the outcome (created / updated /
    held) after the page reloads on its own — closing the "the button vanished
    and nothing shows" gap that made a working repair look inert. Reads the
    ``apply_totals`` the orchestrator persists; skips a dry-run's totals (a
    preview writes nothing) and returns ``None`` when nothing has been applied.
    """
    totals = (getattr(bundle, "mapping_summary", None) or {}).get("apply_totals") or {}
    if not totals or totals.get("dry_run"):
        return None
    created = int(totals.get("created") or 0)
    updated = int(totals.get("updated") or 0)
    held = int(totals.get("quarantined") or 0)
    if created == 0 and updated == 0 and held == 0:
        return None
    return {
        "created": created,
        "updated": updated,
        "held": held,
        "applied_at": totals.get("applied_at") or "",
    }


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
        bundle = _tenant_bundle_or_404(request, bundle_id)
        confirmed = str(request.POST.get("confirm", "")).lower() in ("1", "true", "yes", "on")
        dry_run = not confirmed
        try:
            from .celery_tasks import enqueue_apply

            result = enqueue_apply(bundle.pk, dry_run=dry_run)
            messages.info(
                request,
                (
                    "Import queued (dry-run)."
                    if dry_run
                    else "Import queued. Refresh shortly for results."
                ),
            )
            return redirect(
                _connector_reverse(request, "bundle-review", bundle_id=bundle.pk)
                + f"?queued=1&outbox={getattr(result, 'outbox_id', '')}"
            )
        except ValueError as exc:
            messages.error(
                request,
                f"This upload isn't ready to import yet ({exc}). Give auto-detect a "
                "moment, refresh, then try again.",
            )
            return redirect(_connector_reverse(request, "bundle-review", bundle_id=bundle.pk))


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
        # Never run apply_bundle on the HTTP thread — durable outbox only.
        result = repair_bundle(bundle_id=bundle.pk, off_http=True)
        bundle.refresh_from_db()

        if result.queued:
            messages.info(request, result.message)
        elif not result.ran:
            messages.info(request, result.message)
        elif result.ok:
            messages.success(request, result.message)
        else:
            messages.error(request, result.message)

        # Only surface the results/verification banner when the repair actually
        # re-imported cleanly on this request; queued repairs refresh later.
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


def _build_rollback(bundle):
    """Compact rollback affordance for the review page.

    Shows a "Revert this import" control once a LIVE apply has landed rows into the
    school. Returns ``None`` (panel hidden) when nothing has been applied yet — a
    fresh upload or a dry-run preview — so the panel only appears when there is
    something to revert. Honest by construction: it names how many rows the import
    created and flags that in-place updates / shared academic scaffold may not be
    auto-reverted (the precise per-domain "what was left in place" comes back on the
    rollback result). Cheap read-only; never raises.
    """
    try:
        totals = (getattr(bundle, "mapping_summary", None) or {}).get("apply_totals") or {}
        if totals.get("dry_run"):
            return None
        created = int(totals.get("created") or 0)
        updated = int(totals.get("updated") or 0)
        if created == 0 and updated == 0:
            return None
        return {"created": created, "updated": updated, "has_updates": updated > 0}
    except Exception:  # noqa: BLE001 — a posture hiccup must never break the page
        logger.debug("tenant rollback: posture failed for %s", bundle.pk, exc_info=True)
        return None


class TenantMigrationRollbackView(_TenantAdminWriteRequiredMixin, View):
    """POST → revert everything an import applied into the caller's OWN school.

    Tenant-admin gated (write + DESTRUCTIVE): a full-bundle rollback DELETES the rows
    this import created, so a non-admin member is refused (403). Requires an explicit
    ``confirm=1`` (the review page's rollback control is a two-step confirm), exactly
    like the live-import guard. Tenant-scoped (cross-tenant id → 404);
    ``@idempotent_post`` collapses an accidental double-submit into one rollback.

    All the revert judgement lives in
    :func:`services.connector_rollback.rollback_bundle` — the shared, child-first,
    HONEST revert that reports which domains it could NOT auto-revert (shared academic
    scaffold, in-place updates, PROTECT-blocked rows). The source data is never
    touched — only rows this import created in the school are removed.
    """

    template_name = "migration_cloud/connector/bundle_review.html"

    @idempotent_post
    @safe_500
    def post(self, request, bundle_id: int):
        from .services.connector_rollback import rollback_bundle

        bundle = _tenant_bundle_or_404(request, bundle_id)
        confirmed = str(request.POST.get("confirm", "")).lower() in ("1", "true", "yes", "on")
        if not confirmed:
            messages.info(
                request,
                "Rollback needs confirmation — tick the confirm box, then revert.",
            )
            return redirect(_connector_reverse(request, "bundle-review", bundle_id=bundle.pk))

        result = rollback_bundle(bundle=bundle, actor=request.user, confirm=True)

        if not result.get("applied"):
            messages.info(request, result.get("message") or "Nothing to roll back.")
        elif result.get("ok"):
            messages.success(request, result.get("message") or "Import reverted.")
        else:
            # Applied but not a clean slate (some domains left in place). Warn — this
            # is an honest partial outcome, not an error; result.message says what.
            messages.warning(
                request,
                result.get("message") or "Rollback partly completed; some rows were left in place.",
            )
        return redirect(_connector_reverse(request, "bundle-review", bundle_id=bundle.pk))
