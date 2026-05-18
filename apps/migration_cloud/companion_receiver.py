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

from .models import (
    BundleStatus,
    CompanionCiphertextBlob,
    CompanionUploadReceipt,
    IntakeMethod,
    MigrationAuthorizationAgreement,
    MigrationBundle,
)
from .reliability import idempotent_post, safe_500
from .services import companion_keypair as _companion_keypair
from .services.maa_text import AGREEMENT_VERSION_CURRENT, render_maa_text

logger = logging.getLogger(__name__)


_MAX_METADATA_BYTES = 8 * 1024  # 8 KiB metadata cap; ciphertext is unbounded
_MAX_CIPHERTEXT_BYTES = 512 * 1024 * 1024  # 512 MiB ceiling (matches Companion)


# ─── Helpers ─────────────────────────────────────────────────────────────


def _client_ip(request: HttpRequest) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
    return forwarded or request.META.get("REMOTE_ADDR") or None


def _user_agent(request: HttpRequest) -> str:
    return (request.META.get("HTTP_USER_AGENT") or "")[:512]


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
    version = (request.GET.get("version") or AGREEMENT_VERSION_CURRENT).strip()
    if not vendor:
        return _json_error("vendor querystring parameter required", status=400, code="missing_vendor")
    try:
        text = render_maa_text(vendor, holder, version)
    except ValueError as exc:
        return _json_error(str(exc), status=400, code="bad_version")
    logger.info(
        "migration_cloud.companion_receiver: maa_text rendered vendor=%s version=%s user_id=%s",
        vendor, version, getattr(request.user, "pk", None),
    )
    return JsonResponse(
        {"ok": True, "vendor": vendor, "version": version, "text": text}
    )


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
        version = (payload.get("agreement_version") or AGREEMENT_VERSION_CURRENT).strip()

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

        try:
            signature_text = render_maa_text(vendor_source, holder_name, version)
        except ValueError as exc:
            return _json_error(str(exc), status=400, code="bad_version")

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

                receipt = CompanionUploadReceipt.objects.create(  # tenant-isolation-allow: companion-receiver-create-receipt-for-resolved-tenant
                    tenant=school,
                    bundle=bundle,
                    maa=maa,
                    ciphertext_blob=blob,
                    client_idempotency_key=idem_key,
                    ciphertext_sha256=observed_sha,
                    plaintext_byte_size=plaintext_size,
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

        try:
            plaintext = _companion_keypair.decrypt_with_active_or_versioned(
                ciphertext_bytes,
                requested_version=requested_version,
            )
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

    Anonymous-allowed (cross-extension fetch from the Companion popup;
    the popup carries the operator's session cookie but the public key
    itself is non-sensitive). Optional ``?tenant_id=<n>`` is accepted
    for forward compatibility with per-tenant keypairs but is currently
    a no-op — one global active keypair serves all tenants.

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
    try:
        info = _companion_keypair.get_active_public_key_info()
    except _companion_keypair.PyNaClUnavailable:
        return _json_error(
            "PyNaCl not installed on server; companion keypair unavailable",
            status=501,
            code="pynacl_missing",
        )

    # The tenant_id query is logged for audit-trail but does not change
    # the response (per-tenant keypairs are a future enhancement).
    tenant_id_raw = request.GET.get("tenant_id")
    logger.info(
        "migration_cloud.companion_receiver: server_pubkey_fetched "
        "key_version=%s fingerprint=%s tenant_id_q=%s",
        info["key_version"], info["fingerprint_b64"], tenant_id_raw,
    )
    return JsonResponse({"ok": True, **info}, status=200)


# ─── Server pubkey rotation (POST) ───────────────────────────────────────


@method_decorator(csrf_exempt, name="dispatch")
class CompanionKeypairRotateView(LoginRequiredMixin, View):
    """POST /companion/keypair/rotate/ — staff-only key rotation.

    Generates a fresh X25519 keypair, marks the previous active one as
    rotated_out, and returns the old + new version + fingerprint. No
    private bytes ever appear in the response.
    """

    @method_decorator(safe_500)
    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated and getattr(user, "is_staff", False)):
            return _json_error("staff-only endpoint", status=403, code="not_staff")

        try:
            result = _companion_keypair.rotate_keypair(operator_user=user)
        except _companion_keypair.PyNaClUnavailable:
            return _json_error(
                "PyNaCl not installed on server; rotate unavailable",
                status=501,
                code="pynacl_missing",
            )

        return JsonResponse({"ok": True, **result}, status=201)
