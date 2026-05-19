"""Companion-extension upload receiver (v3.29.0 Agent 2).

Three operator-flow endpoints that hand off encrypted ``CanonicalBundle``
payloads from the Companion browser extension to the existing v3.28.0
wizard pipeline:

    POST /companion/maa/sign/        — sign a Migration Authorization
                                       Agreement before any upload.
    GET  /companion/maa/text/        — fetch the verbatim MAA text the
                                       popup will display.
    POST /companion/upload/          — multipart upload of the
                                       libsodium-sealed ciphertext +
                                       metadata.
    POST /companion/decrypt/<id>/    — staff-only in-memory decrypt
                                       hook; private key never persists.

Defense layers:

  * MAA must exist, not be revoked, match tenant + vendor.
  * Ciphertext SHA-256 must match metadata-supplied digest (integrity).
  * ``client_idempotency_key`` is unique, so replays return the prior
    receipt rather than creating a second bundle.
  * Every ciphertext blob is stored under
    ``companion_uploads/<tenant_id>/<uuid>.bin`` in Django default
    storage; bytes are never logged.
  * Logger emissions carry IDs and lengths only — NEVER ciphertext
    bytes, plaintext content, encryption keys, or MAA signature_text.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from typing import Any

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import metrics as _mc_metrics
from .models import (
    BundleStatus,
    CompanionCiphertextBlob,
    CompanionUploadReceipt,
    IntakeMethod,
    MigrationAuthorizationAgreement,
    MigrationBundle,
)
# v3.38.0 Agent 5 — append-only audit emissions.
from .models_audit import MigrationCloudAuditEvent as _AuditEvent
from .reliability import idempotent_post, safe_500
from .services import companion_keypair as _companion_keypair
from .services.maa_text import (
    AGREEMENT_VERSION_CURRENT,
    MAA_TEXT_DRAFT_VERSIONS,
    is_draft_version,
    render_maa_text,
    resolve_active_version_for_tenant,
    resolve_preview_version_for_tenant,
)

logger = logging.getLogger(__name__)


_MAX_METADATA_BYTES = 8 * 1024  # 8 KiB metadata cap; ciphertext is unbounded
_MAX_CIPHERTEXT_BYTES = 512 * 1024 * 1024  # 512 MiB ceiling (matches Companion)


# ─── Helpers ─────────────────────────────────────────────────────────────


def _client_ip(request: HttpRequest) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
    return forwarded or request.META.get("REMOTE_ADDR") or None


def _user_agent(request: HttpRequest) -> str:
    return (request.META.get("HTTP_USER_AGENT") or "")[:512]


def _constant_time_eq(a: str, b: str) -> bool:
    """Constant-time string equality (defence-in-depth for sha digests)."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _safe_audit(tenant_slug: str, event_type: str, **kwargs) -> None:
    """v3.38.0 — append an audit event; NEVER let failure break production.

    Audit emission is best-effort: a DB-level failure here would
    otherwise turn a successful sign / upload into a 500. We log at
    ERROR (audit failure is more serious than metric failure) and
    swallow the exception. The integrity gap is detectable by the
    verify_audit_chain command.
    """
    try:
        _AuditEvent.objects.record(tenant_slug, event_type, **kwargs)
    except Exception as exc:  # broad-by-design: audit must never break flow
        logger.error(
            "migration_cloud.audit: emit failed event_type=%s err=%s",
            event_type, type(exc).__name__,
        )


def _request_school(request: HttpRequest):
    """Resolve the tenant scope for the current request.

    Mirrors the convention used in ``views.py``: portal shells bind
    ``request.school`` or ``request.tenant``; operator shells may
    delegate via the user's primary membership. Returns ``None`` if
    no scope is available — callers must 403.
    """
    school = getattr(request, "school", None) or getattr(request, "tenant", None)
    if school is not None:
        return school
    # Fallback: first SchoolMembership for the user (operator shell helper).
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    membership_mgr = getattr(user, "school_memberships", None)
    if membership_mgr is None:
        return None
    membership = (
        # tenant-isolation-allow: companion-receiver-resolve-actor-membership-via-user-fk
        membership_mgr.select_related("school").first()
    )
    return getattr(membership, "school", None) if membership else None


def _parse_metadata(raw: bytes | str) -> dict[str, Any]:
    if isinstance(raw, bytes):
        if len(raw) > _MAX_METADATA_BYTES:
            raise ValueError("metadata payload too large")
        raw = raw.decode("utf-8")
    try:
        parsed = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"metadata JSON parse failed: {type(exc).__name__}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("metadata must be a JSON object")
    return parsed


def _json_error(message: str, *, status: int, code: str | None = None) -> JsonResponse:
    body: dict[str, Any] = {"ok": False, "error": message}
    if code:
        body["code"] = code
    return JsonResponse(body, status=status)


def _next_step_url(bundle_id: int) -> str:
    """Best-effort hint at the wizard URL the operator should visit next.

    Returns a string path; the Companion popup uses it to deep-link the
    operator into the wizard after a successful upload. We can't use
    ``reverse()`` because the route lives under two mount points; we
    construct the operator-shell path by convention.
    """
    return f"/super/migration/{bundle_id}/"


# ─── MAA text (GET) ──────────────────────────────────────────────────────


@require_GET
@login_required
@safe_500
def maa_text_view(request: HttpRequest) -> JsonResponse:
    """Return verbatim MAA text for popup display.

    Querystring:
      vendor=<vendor_source>
      holder=<vendor_account_holder_name>   (optional; defaults to "(unknown account holder)")
      version=<agreement_version>           (optional; defaults to current)
    """
    vendor = (request.GET.get("vendor") or "").strip()
    holder = (request.GET.get("holder") or "").strip()
    explicit_version = (request.GET.get("version") or "").strip()
    if not vendor:
        return _json_error("vendor querystring parameter required", status=400, code="missing_vendor")

    # v3.34.0 — resolve the tenant-aware ACTIVE version (always non-draft;
    # see resolve_active_version_for_tenant docstring for the safety
    # contract). Preview is opt-in-only and never binds. If the caller
    # passes ?version=<x> explicitly we honor that for rendering only;
    # the active version that the server would actually sign remains the
    # tenant-resolved one.
    tenant = _request_school(request)
    active_version = resolve_active_version_for_tenant(tenant)
    preview_version = resolve_preview_version_for_tenant(tenant)

    # If no explicit version was passed, render the active version body.
    # If one was passed, render that body — useful for the preview path
    # where the popup wants to see the draft text. The "version" field
    # in the response always reports what was actually rendered.
    version = explicit_version or active_version

    try:
        text = render_maa_text(vendor, holder, version)
    except ValueError as exc:
        return _json_error(str(exc), status=400, code="bad_version")
    is_draft = is_draft_version(version)

    preview_payload: dict[str, Any] | None = None
    if preview_version is not None:
        try:
            preview_text = render_maa_text(vendor, holder, preview_version)
        except ValueError:
            preview_text = ""
        preview_payload = {
            "version": preview_version,
            "text": preview_text,
            "is_preview": True,
            "preview_banner": "PREVIEW — not yet active",
        }

    logger.info(
        "migration_cloud.companion_receiver: maa_text rendered vendor=%s version=%s "
        "active_version=%s preview_version=%s user_id=%s draft=%s",
        vendor, version, active_version, preview_version,
        getattr(request.user, "pk", None), is_draft,
    )
    response: dict[str, Any] = {
        "ok": True,
        "vendor": vendor,
        "version": version,
        "text": text,
        "is_draft": is_draft,
        "active_version": active_version,
        # UI must render a "Draft — preview only" banner when is_draft is True.
        "draft_banner": (
            "DRAFT — pending counsel review. Preview only; "
            "this version is not legally binding."
            if is_draft
            else ""
        ),
    }
    if preview_payload is not None:
        response["preview"] = preview_payload
    return JsonResponse(response)


# ─── MAA sign (POST) ─────────────────────────────────────────────────────


@method_decorator(csrf_exempt, name="dispatch")
class MAASignView(LoginRequiredMixin, View):
    """POST /companion/maa/sign/ — create a new authorization agreement."""

    @method_decorator(idempotent_post)
    @method_decorator(safe_500)
    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        try:
            payload = _parse_metadata(request.body or b"{}")
        except ValueError as exc:
            logger.warning(
                "migration_cloud.companion_receiver: maa_sign bad_json user_id=%s err=%s",
                getattr(request.user, "pk", None), type(exc).__name__,
            )
            return _json_error("invalid JSON body", status=400, code="bad_json")

        vendor_source = (payload.get("vendor_source") or "").strip()
        holder_name = (payload.get("vendor_account_holder_name") or "").strip()
        role = (payload.get("signed_by_role") or "").strip()
        requested_version = (
            payload.get("agreement_version") or ""
        ).strip()
        # v3.34.0 — operator MAY include the rendered signature_text in
        # the POST so the server can verify byte-for-byte equality with
        # the active-version body. This catches:
        #   (a) UI rendering a preview body and accidentally posting it
        #   (b) Tampering between render and sign
        # When omitted, the server renders + captures the active body
        # itself (backwards-compatible with v3.33 callers).
        submitted_signature_text = payload.get("submitted_signature_text")
        if submitted_signature_text is not None and not isinstance(
            submitted_signature_text, str
        ):
            return _json_error(
                "submitted_signature_text must be a string",
                status=400,
                code="bad_signature_text",
            )

        if not vendor_source or not holder_name or not role:
            return _json_error(
                "vendor_source, vendor_account_holder_name, signed_by_role are required",
                status=400,
                code="missing_fields",
            )

        school = _request_school(request)
        if school is None:
            logger.warning(
                "migration_cloud.companion_receiver: maa_sign denied no_tenant user_id=%s",
                getattr(request.user, "pk", None),
            )
            return _json_error(
                "no tenant membership for requesting user",
                status=403,
                code="no_tenant",
            )

        # v3.34.0 — the version that actually binds is the tenant-resolved
        # ACTIVE version (always non-draft). If the operator explicitly
        # passed a different agreement_version we cross-check: if they
        # asked for the active version, fine; if they asked for a draft
        # version they get refused; if they asked for a different
        # non-draft version we honor it only when it matches the
        # active resolver result.
        active_version = resolve_active_version_for_tenant(school)
        version = requested_version or active_version

        # v3.33.0 — refuse to sign a draft version. Drafts may be
        # PREVIEWED via the maa_text endpoint with ?version=v2.0 but
        # cannot bind the operator until counsel review advances them
        # out of the draft set and AGREEMENT_VERSION_CURRENT moves
        # forward.
        if is_draft_version(version):
            logger.warning(
                "migration_cloud.companion_receiver: maa_sign refused_draft "
                "user_id=%s version=%s",
                getattr(request.user, "pk", None), version,
            )
            try:
                _mc_metrics.record_maa_sign(
                    tenant_id=getattr(school, "pk", None),
                    version=version,
                    was_draft_attempt=True,
                )
            except Exception as _metric_exc:  # noqa: BLE001
                logger.warning(
                    "migration_cloud.companion_receiver: maa_sign_metric_failed err=%s",
                    type(_metric_exc).__name__,
                )
            _safe_audit(
                getattr(school, "slug", "") or "",
                "maa.sign_attempt_draft",
                actor=request.user,
                subject=None,
                payload_summary={
                    "vendor_source": vendor_source[:64],
                    "agreement_version_attempted": version[:32],
                    "refused": True,
                },
            )
            return _json_error(
                "agreement_version is a DRAFT — preview only; cannot be signed.",
                status=400,
                code="draft_version",
            )

        # v3.34.0 — if the caller passed a non-draft version that
        # diverges from the tenant-resolved active version, refuse so
        # opt-in tenants can't drift to a different non-draft body by
        # client-side request. The active version is the SOURCE OF
        # TRUTH for what binds.
        if requested_version and requested_version != active_version:
            logger.warning(
                "migration_cloud.companion_receiver: maa_sign version_mismatch "
                "user_id=%s requested=%s active=%s",
                getattr(request.user, "pk", None),
                requested_version, active_version,
            )
            return _json_error(
                "requested agreement_version does not match the tenant-active "
                "version; refresh the sign page and retry.",
                status=400,
                code="version_mismatch",
            )

        try:
            signature_text = render_maa_text(vendor_source, holder_name, version)
        except ValueError as exc:
            return _json_error(str(exc), status=400, code="bad_version")

        # v3.34.0 — when the operator submitted a signature_text body,
        # verify it matches the server-rendered active-version body
        # byte-for-byte. Drift here means the client rendered the
        # preview (draft) and is trying to bind it — refuse with
        # ``draft_signature_attempt``. Boolean presence + sha prefix
        # are logged; the bodies themselves are NEVER logged.
        if submitted_signature_text is not None:
            submitted_sha = hashlib.sha256(
                submitted_signature_text.encode("utf-8")
            ).hexdigest()
            expected_sha = hashlib.sha256(
                signature_text.encode("utf-8")
            ).hexdigest()
            if not _constant_time_eq(submitted_sha, expected_sha):
                # Determine whether the submitted body matches ANY draft
                # version body — that tells us the caller tried to bind
                # the preview, which is the explicit failure code the
                # spec calls for.
                looks_like_draft = False
                for draft_v in MAA_TEXT_DRAFT_VERSIONS:
                    try:
                        draft_body = render_maa_text(
                            vendor_source, holder_name, draft_v,
                        )
                    except ValueError:
                        continue
                    draft_sha = hashlib.sha256(
                        draft_body.encode("utf-8"),
                    ).hexdigest()
                    if _constant_time_eq(submitted_sha, draft_sha):
                        looks_like_draft = True
                        break
                logger.warning(
                    "migration_cloud.companion_receiver: maa_sign "
                    "signature_text_mismatch user_id=%s submitted_sha_prefix=%s "
                    "expected_sha_prefix=%s looks_like_draft=%s",
                    getattr(request.user, "pk", None),
                    submitted_sha[:12], expected_sha[:12], looks_like_draft,
                )
                if looks_like_draft:
                    return _json_error(
                        "submitted signature_text matches a DRAFT version "
                        "body; drafts cannot be signed.",
                        status=400,
                        code="draft_signature_attempt",
                    )
                return _json_error(
                    "submitted_signature_text does not match the "
                    "server-rendered active-version body.",
                    status=400,
                    code="signature_text_mismatch",
                )

        maa = MigrationAuthorizationAgreement.objects.create(  # tenant-isolation-allow: companion-receiver-create-maa-for-resolved-tenant
            tenant=school,
            signed_by_user=request.user,
            signed_by_role=role[:128],
            vendor_source=vendor_source[:64],
            vendor_account_holder_name=holder_name[:256],
            agreement_version=version[:32],
            signature_text=signature_text,
            client_ip=_client_ip(request),
            user_agent=_user_agent(request),
        )
        logger.info(
            "migration_cloud.companion_receiver: maa_signed maa_id=%s tenant_id=%s vendor=%s version=%s",
            maa.pk, school.pk, vendor_source, version,
        )
        # v3.38.0 — operational metrics (best-effort; never breaks the
        # hot path). Helper itself try/excepts internally; the outer
        # try/except here is defense-in-depth in case import-time
        # binding ever fails.
        try:
            _mc_metrics.record_maa_sign(
                tenant_id=school.pk, version=version, was_draft_attempt=False,
            )
        except Exception as _metric_exc:  # noqa: BLE001
            logger.warning(
                "migration_cloud.companion_receiver: maa_sign_metric_failed err=%s",
                type(_metric_exc).__name__,
            )
        # v3.38.0 Agent 5 — append-only audit emission for MAA sign.
        _safe_audit(
            getattr(school, "slug", "") or "",
            "maa.sign",
            actor=request.user,
            subject=maa.pk,
            payload_summary={
                "vendor_source": vendor_source[:64],
                "agreement_version": version[:32],
                "signed_by_role": role[:64],
            },
        )
        return JsonResponse(
            {
                "ok": True,
                "maa_id": maa.pk,
                "signed_at": maa.signed_at.isoformat(),
                "agreement_version": maa.agreement_version,
            },
            status=201,
        )


# ─── Companion upload (POST multipart) ───────────────────────────────────


@method_decorator(csrf_exempt, name="dispatch")
class CompanionUploadView(LoginRequiredMixin, View):
    """POST /companion/upload/ — accept the encrypted bundle ciphertext.

    Multipart fields:
      ciphertext  (binary)
      metadata    (JSON: {maa_id, client_idempotency_key, vendor_source,
                          ciphertext_sha256, plaintext_byte_size})
    """

    @method_decorator(safe_500)
    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        # Parse + validate metadata.
        try:
            metadata_raw = request.POST.get("metadata") or ""
            payload = _parse_metadata(metadata_raw)
        except ValueError as exc:
            logger.warning(
                "migration_cloud.companion_receiver: upload bad_metadata user_id=%s err=%s",
                getattr(request.user, "pk", None), type(exc).__name__,
            )
            return _json_error("invalid metadata", status=400, code="bad_metadata")

        maa_id = payload.get("maa_id")
        idem_key = (payload.get("client_idempotency_key") or "").strip()
        vendor_source = (payload.get("vendor_source") or "").strip()
        declared_sha = (payload.get("ciphertext_sha256") or "").strip().lower()
        plaintext_size = payload.get("plaintext_byte_size") or 0
        # v3.32.0 — Companion now tags each upload with the server keypair
        # version it sealed against. Receiver acknowledges + logs the tag
        # so the decrypt hook can pin to that version after rotation.
        # The receipt model does not persist it (would require a follow-up
        # migration); the active row's version is the default fallback at
        # decrypt time.
        key_version_tag = (payload.get("key_version") or "").strip() or None
        try:
            plaintext_size = int(plaintext_size)
        except (TypeError, ValueError):
            plaintext_size = 0

        if not (isinstance(maa_id, int) and idem_key and vendor_source and declared_sha):
            return _json_error(
                "maa_id, client_idempotency_key, vendor_source, ciphertext_sha256 required",
                status=400,
                code="missing_fields",
            )
        if len(declared_sha) != 64:
            return _json_error("ciphertext_sha256 must be 64-char hex", status=400, code="bad_sha")

        # Idempotency replay short-circuit (before reading the ciphertext).
        existing = (
            CompanionUploadReceipt.objects  # tenant-isolation-allow: companion-receiver-idempotency-lookup-by-unique-key
            .select_related("bundle", "maa")
            .filter(client_idempotency_key=idem_key)
            .first()
        )
        if existing is not None:
            logger.info(
                "migration_cloud.companion_receiver: upload idempotency_replay receipt_id=%s bundle_id=%s",
                existing.pk, existing.bundle_id,
            )
            return JsonResponse(
                {
                    "ok": True,
                    "replay": True,
                    "bundle_id": existing.bundle_id,
                    "receipt_id": existing.pk,
                    "status": existing.bundle.status if existing.bundle else "unknown",
                    "next_step_url": _next_step_url(existing.bundle_id),
                },
                status=200,
            )

        # Resolve tenant.
        school = _request_school(request)
        if school is None:
            return _json_error("no tenant membership", status=403, code="no_tenant")

        # Resolve MAA, check active + matches tenant + vendor.
        try:
            maa = MigrationAuthorizationAgreement.objects.get(  # tenant-isolation-allow: companion-receiver-fetch-maa-then-verify-tenant-match
                pk=maa_id,
            )
        except MigrationAuthorizationAgreement.DoesNotExist:
            return _json_error("MAA not found", status=404, code="maa_not_found")
        if maa.tenant_id != school.pk:
            logger.warning(
                "migration_cloud.companion_receiver: upload tenant_mismatch maa_id=%s maa_tenant=%s req_tenant=%s",
                maa.pk, maa.tenant_id, school.pk,
            )
            return _json_error("MAA tenant mismatch", status=403, code="maa_tenant_mismatch")
        if maa.vendor_source != vendor_source:
            return _json_error(
                "MAA vendor mismatch", status=403, code="maa_vendor_mismatch",
            )
        if maa.revoked_at is not None:
            return _json_error(
                "MAA has been revoked", status=409, code="maa_revoked",
            )

        # Read ciphertext from multipart.
        ciphertext_file = request.FILES.get("ciphertext")
        if ciphertext_file is None:
            return _json_error("ciphertext file part required", status=400, code="missing_ciphertext")
        if ciphertext_file.size > _MAX_CIPHERTEXT_BYTES:
            return _json_error(
                f"ciphertext exceeds {_MAX_CIPHERTEXT_BYTES}-byte ceiling",
                status=413,
                code="ciphertext_too_large",
            )

        # Stream-hash the ciphertext to verify integrity.
        hasher = hashlib.sha256()
        total = 0
        chunks: list[bytes] = []
        for chunk in ciphertext_file.chunks():
            hasher.update(chunk)
            total += len(chunk)
            chunks.append(chunk)
        observed_sha = hasher.hexdigest()
        if observed_sha != declared_sha:
            logger.warning(
                "migration_cloud.companion_receiver: upload sha_mismatch declared=%s observed=%s size=%s",
                declared_sha[:12], observed_sha[:12], total,
            )
            return _json_error(
                "ciphertext SHA-256 does not match metadata",
                status=400,
                code="sha_mismatch",
            )

        # Persist: blob file, bundle (pending_decrypt), receipt — atomically.
        blob_filename = f"{uuid.uuid4().hex}.bin"
        blob_relpath = f"{school.pk}/{blob_filename}"
        try:
            with transaction.atomic():
                blob = CompanionCiphertextBlob(  # tenant-isolation-allow: companion-receiver-create-blob-for-resolved-tenant
                    tenant=school,
                    ciphertext_sha256=observed_sha,
                    byte_size=total,
                )
                blob.blob_file.save(blob_relpath, ContentFile(b"".join(chunks)), save=False)
                blob.save()

                bundle = MigrationBundle.objects.create(  # tenant-isolation-allow: companion-receiver-create-bundle-for-resolved-tenant
                    school=school,
                    label=f"Companion upload — {vendor_source}",
                    intake_method=IntakeMethod.FILE_UPLOAD,
                    intake_source_uri=f"companion://{vendor_source}/{idem_key[:16]}",
                    source_hint=vendor_source,
                    idempotency_key=f"companion:{idem_key}",
                    status=BundleStatus.PENDING,
                    triggered_by=request.user,
                )

                # v3.33.0 — record the client-supplied ``key_version``
                # tag on the receipt at upload time so an auditor can
                # answer "which server key half opened receipt R?" even
                # before the decrypt hook runs. The decrypt hook later
                # overwrites this field with the version that ACTUALLY
                # opened the SealedBox (may differ from the tag after a
                # rotation when the client signalled the new version
                # but the upload arrived before the decrypt did).
                receipt = CompanionUploadReceipt.objects.create(  # tenant-isolation-allow: companion-receiver-create-receipt-for-resolved-tenant
                    tenant=school,
                    bundle=bundle,
                    maa=maa,
                    ciphertext_blob=blob,
                    client_idempotency_key=idem_key,
                    ciphertext_sha256=observed_sha,
                    plaintext_byte_size=plaintext_size,
                    key_version=(key_version_tag or "")[:16],
                )
        except IntegrityError:
            # Race: another request used the same idempotency key while we
            # were hashing. Re-look up + replay.
            existing = (
                CompanionUploadReceipt.objects  # tenant-isolation-allow: companion-receiver-idempotency-race-recovery-lookup
                .select_related("bundle")
                .filter(client_idempotency_key=idem_key)
                .first()
            )
            if existing is not None:
                return JsonResponse(
                    {
                        "ok": True,
                        "replay": True,
                        "bundle_id": existing.bundle_id,
                        "receipt_id": existing.pk,
                        "status": existing.bundle.status if existing.bundle else "unknown",
                        "next_step_url": _next_step_url(existing.bundle_id),
                    },
                    status=200,
                )
            return _json_error("upload conflicted", status=409, code="integrity_error")

        logger.info(
            "migration_cloud.companion_receiver: upload accepted receipt_id=%s bundle_id=%s "
            "tenant_id=%s vendor=%s ciphertext_size=%s sha_prefix=%s key_version=%s",
            receipt.pk, bundle.pk, school.pk, vendor_source, total, observed_sha[:12],
            key_version_tag,
        )
        # v3.38.0 Agent 5 — append-only audit emission for upload accept.
        _safe_audit(
            getattr(school, "slug", "") or "",
            "companion.upload",
            actor=request.user,
            subject=receipt.client_idempotency_key,
            payload_summary={
                "byte_count": int(total or 0),
                "scheme": str(payload.get("encryption_scheme") or "")[:64],
                "vendor_source": vendor_source[:64],
                "ciphertext_sha_prefix": observed_sha[:12],
            },
        )
        # v3.38.0 — operational metrics. ``total`` is the integer byte
        # count of ciphertext, never the bytes themselves.
        try:
            _mc_metrics.record_companion_upload(
                tenant_id=school.pk,
                byte_size=total,
                sealed_box_scheme="libsodium-secretbox-x25519-sealed",
            )
        except Exception as _metric_exc:  # noqa: BLE001
            logger.warning(
                "migration_cloud.companion_receiver: upload_metric_failed err=%s",
                type(_metric_exc).__name__,
            )
        return JsonResponse(
            {
                "ok": True,
                "replay": False,
                "bundle_id": bundle.pk,
                "receipt_id": receipt.pk,
                "status": bundle.status,
                "next_step_url": _next_step_url(bundle.pk),
            },
            status=201,
        )


# ─── Staff-driven decrypt hook ───────────────────────────────────────────


@method_decorator(csrf_exempt, name="dispatch")
class CompanionDecryptHookView(LoginRequiredMixin, View):
    """POST /companion/decrypt/<bundle_id>/ — staff-driven decrypt.

    v3.32.0: the server now owns the X25519 keypair (see
    :mod:`apps.migration_cloud.services.companion_keypair`). The
    operator no longer pastes private bytes; the view calls
    :func:`decrypt_with_active_or_versioned` which unwraps the
    encrypted-at-rest private bytes, opens the SealedBox once, then
    zeroes the in-memory plaintext key.

    Optional body fields:
      ``key_version`` — when supplied, pin decrypt to a specific keypair
                         row (useful for old ciphertext after rotation).
    """

    @method_decorator(safe_500)
    def post(self, request: HttpRequest, bundle_id: int, *args, **kwargs) -> JsonResponse:
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated and getattr(user, "is_staff", False)):
            return _json_error("staff-only endpoint", status=403, code="not_staff")

        try:
            payload = _parse_metadata(request.body or b"{}")
        except ValueError:
            return _json_error("invalid JSON body", status=400, code="bad_json")

        requested_version = payload.get("key_version")
        if requested_version is not None and not isinstance(requested_version, str):
            return _json_error("key_version must be a string", status=400, code="bad_version")

        try:
            bundle = MigrationBundle.objects.get(pk=bundle_id)  # tenant-isolation-allow: companion-receiver-decrypt-staff-only-bundle-lookup
        except MigrationBundle.DoesNotExist:
            return _json_error("bundle not found", status=404, code="bundle_not_found")

        receipt = (
            CompanionUploadReceipt.objects  # tenant-isolation-allow: companion-receiver-decrypt-receipt-lookup-by-bundle
            .select_related("ciphertext_blob")
            .filter(bundle=bundle)
            .order_by("-received_at")
            .first()
        )
        if receipt is None or receipt.ciphertext_blob is None:
            return _json_error("no ciphertext blob for bundle", status=404, code="no_blob")

        # Read ciphertext bytes from storage. We do NOT log the bytes.
        with receipt.ciphertext_blob.blob_file.open("rb") as fh:
            ciphertext_bytes = fh.read()

        # v3.34.0 — keypairs are per-tenant. Resolve the tenant scope
        # from the bundle (authoritative — set at upload time when the
        # request had its own tenant). Cross-check against the caller's
        # current request.tenant to refuse cross-tenant decrypts: a
        # staff user signed into tenant A cannot trigger decrypt on a
        # bundle belonging to tenant B.
        bundle_tenant = getattr(bundle, "school", None)
        if bundle_tenant is None:
            return _json_error(
                "bundle has no tenant",
                status=409,
                code="bundle_no_tenant",
            )
        caller_school = _request_school(request)
        if caller_school is not None and getattr(caller_school, "pk", None) != getattr(
            bundle_tenant, "pk", None
        ):
            logger.warning(
                "migration_cloud.companion_receiver: decrypt tenant_mismatch "
                "bundle_id=%s bundle_tenant=%s caller_tenant=%s user_id=%s",
                bundle.pk,
                getattr(bundle_tenant, "pk", None),
                getattr(caller_school, "pk", None),
                getattr(user, "pk", None),
            )
            return _json_error(
                "tenant mismatch between bundle and caller",
                status=403,
                code="tenant_mismatch",
            )

        try:
            # v3.34.0 — service requires tenant first arg. Returns a
            # ``DecryptResult`` carrying the keypair version that
            # opened the SealedBox. We persist that version on the
            # receipt so audit trails pin to the exact half-key used
            # (the client-supplied tag stored at upload time may
            # diverge after a rotation).
            decrypt_result = _companion_keypair.decrypt_with_active_or_versioned(
                bundle_tenant,
                ciphertext_bytes,
                key_version=requested_version,
            )
            plaintext = decrypt_result.plaintext
            opened_with_version = decrypt_result.key_version
        except _companion_keypair.PyNaClUnavailable:
            return _json_error(
                "PyNaCl not installed on server; decrypt hook unavailable",
                status=501,
                code="pynacl_missing",
            )
        except (ValueError, TypeError) as exc:
            logger.warning(
                "migration_cloud.companion_receiver: decrypt input_error bundle_id=%s err=%s",
                bundle.pk, type(exc).__name__,
            )
            return _json_error("invalid key material", status=400, code="bad_key")
        except Exception as exc:  # pragma: no cover — nacl CryptoError surfaces here
            logger.warning(
                "migration_cloud.companion_receiver: decrypt failed bundle_id=%s err=%s",
                bundle.pk, type(exc).__name__,
            )
            return _json_error(
                "decryption failed (key or ciphertext invalid)",
                status=400,
                code="decrypt_failed",
            )

        # Mark blob decrypted; persist plaintext as the bundle's intake artifact.
        receipt.ciphertext_blob.decrypted_at = timezone.now()
        receipt.ciphertext_blob.save(update_fields=["decrypted_at"])

        # v3.33.0 — overwrite the receipt's ``key_version`` with the
        # version that actually opened the SealedBox (vs. the client-
        # supplied upload tag). Tracked for audit; never carries
        # private bytes.
        if opened_with_version and opened_with_version != receipt.key_version:
            receipt.key_version = opened_with_version[:16]
            receipt.save(update_fields=["key_version"])

        bundle.intake_source_uri = f"{bundle.intake_source_uri} (decrypted)"
        bundle.status = BundleStatus.INGESTING
        bundle.started_at = bundle.started_at or timezone.now()
        bundle.save(update_fields=["intake_source_uri", "status", "started_at", "updated_at"])

        logger.info(
            "migration_cloud.companion_receiver: decrypted bundle_id=%s receipt_id=%s "
            "plaintext_size=%s",
            bundle.pk, receipt.pk, len(plaintext),
        )

        # We do NOT echo plaintext to the response. Caller picks up the
        # bundle via the existing wizard endpoints.
        return JsonResponse(
            {
                "ok": True,
                "bundle_id": bundle.pk,
                "receipt_id": receipt.pk,
                "plaintext_size": len(plaintext),
                "decrypted_at": receipt.ciphertext_blob.decrypted_at.isoformat(),
                "next_step_url": _next_step_url(bundle.pk),
            },
            status=200,
        )


# ─── Server pubkey distribution (GET) ────────────────────────────────────


@require_GET
def companion_server_pubkey_view(request: HttpRequest) -> JsonResponse:
    """GET /companion/server-pubkey/ — return the active X25519 public key.

    v3.34.0 — keypairs are per-tenant. The tenant is resolved from
    ``request.tenant`` (set by django-tenants schema middleware) or
    ``request.school`` (operator-shell helper). When the request carries
    no tenant scope, returns 400 — the Companion popup MUST sign in
    first so its session cookie lands a tenant.

    v3.35.0 — operators who manage multiple tenants (e.g. a district-
    level admin migrating 5 schools) need to fetch pubkeys for a tenant
    OTHER than the one bound to their session cookie. The view now
    accepts an explicit ``?tenant=<slug>`` query parameter:

      * If ``?tenant=<slug>`` is omitted, fall back to the session-
        resolved tenant (v3.34.0 behavior; backwards-compatible).
      * If ``?tenant=<slug>`` is supplied AND ``request.tenant`` resolves
        AND they differ: 403 ``tenant_mismatch_query_vs_session``. This
        catches the foot-gun where an operator clicks a saved bookmark
        for tenant A while signed into tenant B's subdomain.
      * If ``?tenant=<slug>`` is supplied but the slug does not match
        an active ``School`` row: 404 ``tenant_not_found``. The error
        message intentionally does NOT echo the slug — that would leak
        slug-existence to an unauthenticated probe.

    Public-key material itself is non-sensitive, but issuing the wrong
    tenant's pubkey would let an extension seal data the WRONG tenant
    can open. Resolving via request.tenant (or the explicit-and-verified
    query param) prevents that confusion.

    Response shape::

        {
          "public_key_b64": "<32-byte X25519 pubkey base64>",
          "key_version": "v1",
          "fingerprint_b64": "<sha256(pubkey_b64)[:16] base64>",
          "encryption_scheme": "libsodium-secretbox-x25519-sealed"
        }

    The private key is NEVER returned under any circumstance. The
    response body contains exactly these four string fields plus
    ``ok=True``; the test suite asserts the absence of any "private"
    key in the JSON payload.
    """
    # v3.35.0 — resolve the requested tenant from the query param FIRST,
    # then cross-check against the session tenant. The query-param path
    # supports operators managing multiple tenants from a single browser.
    # v3.37.0 — echo ``tenant_slug`` back in the response so the popup's
    # tenant switcher can confirm WHICH tenant the pubkey belongs to
    # (defense vs. confused-deputy scenarios where the operator thought
    # they were querying tenant A but the cache returned B).
    explicit_slug = (request.GET.get("tenant") or "").strip()
    session_school = _request_school(request)

    requested_school = None
    if explicit_slug:
        from apps.schools.models import School
        requested_school = (
            # tenant-isolation-allow: companion-pubkey-anonymous-fetch-explicit-slug-lookup
            School.objects.filter(slug=explicit_slug, is_active=True).first()
        )
        if requested_school is None:
            # Generic 404; do NOT echo the slug — that would leak
            # slug-existence via differential timing or message text to
            # an unauthenticated caller.
            logger.warning(
                "migration_cloud.companion_receiver: server_pubkey tenant_not_found "
                "user_id=%s slug_prefix=%s",
                getattr(getattr(request, "user", None), "pk", None),
                explicit_slug[:8],
            )
            return _json_error(
                "tenant not found",
                status=404,
                code="tenant_not_found",
            )
        # Cross-check vs session: if both resolve and they differ, refuse.
        if session_school is not None and getattr(session_school, "pk", None) != getattr(
            requested_school, "pk", None
        ):
            logger.warning(
                "migration_cloud.companion_receiver: server_pubkey "
                "tenant_mismatch_query_vs_session user_id=%s "
                "session_pk=%s requested_pk=%s",
                getattr(getattr(request, "user", None), "pk", None),
                getattr(session_school, "pk", None),
                getattr(requested_school, "pk", None),
            )
            return _json_error(
                "session tenant does not match requested tenant; sign "
                "into the correct subdomain or clear the query parameter.",
                status=403,
                code="tenant_mismatch_query_vs_session",
            )
        school = requested_school
    else:
        school = session_school

    if school is None:
        logger.warning(
            "migration_cloud.companion_receiver: server_pubkey denied no_tenant "
            "user_id=%s",
            getattr(getattr(request, "user", None), "pk", None),
        )
        return _json_error(
            "tenant required (sign in to a tenant before fetching pubkey)",
            status=400,
            code="no_tenant",
        )

    # v3.37.0 — when the caller resolved the tenant via ``?tenant=<slug>``
    # (multi-tenant operator path), wrap the keypair fetch in
    # ``schema_context(tenant.schema_name)`` so that any future move of
    # ``MigrationCloudCompanionKeypair`` from SHARED_APPS into TENANT_APPS
    # keeps working without a view-layer rewrite. For the current
    # SHARED_APPS placement the wrap is a defense-in-depth no-op (the FK
    # filter inside the service is the load-bearing isolation).
    schema_name: str | None = None
    if explicit_slug:
        client = getattr(school, "tenant_client", None)
        schema_name = getattr(client, "schema_name", None) if client else None

    try:
        if schema_name:
            try:
                from django_tenants.utils import schema_context  # type: ignore[import-not-found]
            except ImportError:
                info = _companion_keypair.get_active_public_key_info(school)
            else:
                with schema_context(schema_name):
                    info = _companion_keypair.get_active_public_key_info(school)
        else:
            info = _companion_keypair.get_active_public_key_info(school)
    except _companion_keypair.PyNaClUnavailable:
        return _json_error(
            "PyNaCl not installed on server; companion keypair unavailable",
            status=501,
            code="pynacl_missing",
        )

    tenant_slug = getattr(school, "slug", "") or ""
    logger.info(
        "migration_cloud.companion_receiver: server_pubkey_fetched "
        "tenant_pk=%s tenant_slug=%s key_version=%s fingerprint=%s "
        "explicit_query=%s",
        school.pk, tenant_slug, info["key_version"], info["fingerprint_b64"],
        bool(explicit_slug),
    )
    return JsonResponse(
        {"ok": True, "tenant_slug": tenant_slug, **info},
        status=200,
    )


# ─── Server pubkey rotation (POST) ───────────────────────────────────────


@method_decorator(csrf_exempt, name="dispatch")
class CompanionKeypairRotateView(LoginRequiredMixin, View):
    """POST /companion/keypair/rotate/ — staff-only key rotation.

    v3.34.0 — rotation is scoped to ``request.tenant``. A staff user
    can ONLY rotate the keypair of the tenant they're currently bound
    to via session; rotating tenant B from tenant A's portal is not
    possible because the service-layer query filters by tenant_id.

    Generates a fresh X25519 keypair, marks the previous active one as
    rotated_out, and returns the old + new version + fingerprint. No
    private bytes ever appear in the response.
    """

    @method_decorator(safe_500)
    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated and getattr(user, "is_staff", False)):
            return _json_error("staff-only endpoint", status=403, code="not_staff")

        school = _request_school(request)
        if school is None:
            logger.warning(
                "migration_cloud.companion_receiver: keypair_rotate denied no_tenant "
                "user_id=%s",
                getattr(user, "pk", None),
            )
            return _json_error(
                "tenant required for keypair rotation",
                status=400,
                code="no_tenant",
            )

        try:
            result = _companion_keypair.rotate_active_keypair(
                school, operator_user=user
            )
        except _companion_keypair.PyNaClUnavailable:
            return _json_error(
                "PyNaCl not installed on server; rotate unavailable",
                status=501,
                code="pynacl_missing",
            )

        return JsonResponse({"ok": True, **result}, status=201)
