"""v3.40.0 Agent 15 — operator-side MAA v2.0 counsel-activate UI.

Operator workflow:

  1. Counsel signs the v2.0 PDF (out-of-band).
  2. Operator opens ``/super/migration/maa/v2-counsel-activate/``.
     GET issues a short-lived (5-minute TTL) one-time ``confirm_token``
     stored in ``cache`` under a sha256-derived key. The page shows the
     current state ("v2.0 — DRAFT — awaiting activation"), the full
     v2.0 body, and an activation form.
  3. Operator submits POST with:
       * ``counsel_signoff_pdf_url`` — URL to the counsel-signed PDF.
       * ``counsel_attestation_name`` — operator's full legal name.
       * ``counsel_attestation_text`` — operator's verbatim attestation.
         Only the sha256 is persisted; raw text is discarded after
         hashing.
       * ``confirm_token`` — the one-time token issued in GET.
       * ``confirm_typed_phrase`` — the verbatim phrase
         "I AFFIRM MAA V2.0 COUNSEL HAS SIGNED".
  4. On success the singleton row's ``active_version`` flips to
     ``"v2.0"`` and a ``migration.maa.v2_activated_by_operator`` audit
     event is emitted. Subsequent calls to
     ``MASignView`` (v3.33) start binding v2.0.

Hard contracts:
  * Staff-only via ``@method_decorator(require_control_plane_access, ...)``.
  * Token compare via ``hmac.compare_digest``.
  * Counsel attestation TEXT is NEVER persisted or logged — only the
    first 12 chars of its sha256 hex digest land in the audit payload.
  * MAA v2.0 full body content is NEVER logged.
  * One-time token bound to the operator's user id; another user
    cannot replay the same token.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlparse

from django.contrib import messages
from apps.schools.control_plane import require_control_plane_access
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.decorators import method_decorator
from django.views import View

logger = logging.getLogger(__name__)


_CONFIRM_TOKEN_TTL_SECONDS = 300  # 5-minute one-time-token TTL
_CONFIRM_PHRASE = "I AFFIRM MAA V2.0 COUNSEL HAS SIGNED"
_CACHE_KEY_PREFIX = "migration-cloud:maa-counsel-activate:confirm-token:"


def _cache_key(token_sha: str) -> str:
    return f"{_CACHE_KEY_PREFIX}{token_sha}"


def _issue_token(operator_user_id: int | None) -> tuple[str, str]:
    """Issue a fresh confirm token; return ``(plaintext, sha256_prefix)``.

    The plaintext is rendered into the GET form's hidden field. We
    persist sha256(token) + operator_user_id in cache so a POST from a
    different user (e.g., session cookie theft) cannot redeem the
    token. TTL 5 minutes.
    """
    plaintext = secrets.token_urlsafe(48)
    token_sha = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    cache.set(
        _cache_key(token_sha),
        {
            "operator_user_id": int(operator_user_id)
            if operator_user_id is not None
            else None,
            "issued_at": time.time(),
        },
        timeout=_CONFIRM_TOKEN_TTL_SECONDS,
    )
    return plaintext, token_sha[:12]


def _consume_token(plaintext: str, operator_user_id: int | None) -> bool:
    """Constant-time-validate + invalidate the one-time token.

    Returns True when the token is valid AND bound to the same
    operator_user_id. Pops the cache key on success so the token is
    single-use.
    """
    if not plaintext:
        return False
    token_sha = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    key = _cache_key(token_sha)
    record = cache.get(key)
    if record is None:
        return False
    bound_uid = record.get("operator_user_id")
    # Constant-time compare on a fixed-length representation.
    a = str(bound_uid or "").encode("utf-8")
    b = str(operator_user_id or "").encode("utf-8")
    if not hmac.compare_digest(a, b):
        return False
    cache.delete(key)
    return True


def _validate_url(raw: str) -> tuple[bool, str]:
    """Basic http(s) URL validation; returns ``(ok, reason)``."""
    if not raw or len(raw) > 2048:
        return False, "URL must be 1..2048 characters."
    try:
        parsed = urlparse(raw.strip())
    except ValueError:
        return False, "URL could not be parsed."
    if parsed.scheme not in ("http", "https"):
        return False, "URL must use http(s) scheme."
    if not parsed.netloc:
        return False, "URL must include a host."
    return True, ""


def _render_v2_full_text() -> str:
    """Render the v2.0 body with neutral placeholders for the preview UI."""
    from apps.migration_cloud.services.maa_text import render_maa_text

    return render_maa_text(
        vendor_source="(preview-vendor)",
        vendor_account_holder_name="(preview-account-holder)",
        agreement_version="v2.0",
    )


def _current_state_snapshot() -> dict[str, Any]:
    """Read the live ``MAAActiveVersionState`` row + draft set."""
    snapshot: dict[str, Any] = {
        "active_version": "v1.0",
        "is_v2_active": False,
        "is_v2_draft": True,
        "activated_at": None,
        "activated_by_label": "",
        "counsel_signoff_pdf_url": "",
    }
    try:
        from apps.migration_cloud.models_maa_state import MAAActiveVersionState
        from apps.migration_cloud.services.maa_text import get_draft_versions

        row = MAAActiveVersionState.get_row()
        snapshot["active_version"] = (row.active_version or "v1.0").strip()
        snapshot["is_v2_active"] = snapshot["active_version"] == "v2.0"
        snapshot["activated_at"] = row.activated_at
        op = getattr(row, "activated_by_user", None)
        if op is not None:
            snapshot["activated_by_label"] = (
                getattr(op, "get_username", lambda: f"user#{row.activated_by_user_id}")()
            )
        snapshot["counsel_signoff_pdf_url"] = row.counsel_signoff_pdf_url or ""
        snapshot["is_v2_draft"] = "v2.0" in get_draft_versions()
    except Exception as exc:  # noqa: BLE001 — defensive on fresh DB
        logger.warning(
            "maa_counsel_activate_state_unreadable err_type=%s",
            type(exc).__name__,
        )
    return snapshot


@method_decorator(require_control_plane_access, name="dispatch")
class MAACounselActivateView(View):
    """GET + POST /super/migration/maa/v2-counsel-activate/ — counsel-activate UI."""

    template_name = "migration_cloud/operator/maa_counsel_activate.html"

    # ── GET: render current state + activation form ──────────────────

    def get(self, request, *args, **kwargs):
        snapshot = _current_state_snapshot()
        confirm_plaintext, confirm_token_sha_prefix = _issue_token(
            getattr(request.user, "pk", None),
        )
        v2_full_text = ""
        try:
            v2_full_text = _render_v2_full_text()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "maa_counsel_activate_v2_text_render_failed err_type=%s",
                type(exc).__name__,
            )

        # Resolve "back to command center" URL — both shells; absorb the
        # NoReverseMatch defensively so a partial deploy still renders.
        back_url = "#"
        for candidate in (
            "migration_cloud_super:migration_cloud_command_center",
            "migration_cloud_portal:migration_cloud_command_center",
        ):
            try:
                back_url = reverse(candidate)
                break
            except NoReverseMatch:
                continue

        ctx = {
            "shell": kwargs.get("shell", "super"),
            "page_title": "Migration Cloud — MAA v2.0 counsel-activate",
            "state": snapshot,
            "v2_full_text": v2_full_text,
            "confirm_token": confirm_plaintext,
            "confirm_token_sha_prefix": confirm_token_sha_prefix,
            "confirm_phrase_expected": _CONFIRM_PHRASE,
            "back_url": back_url,
            "form_errors": [],
            "form_values": {
                "counsel_signoff_pdf_url": "",
                "counsel_attestation_name": "",
                "confirm_typed_phrase": "",
            },
        }
        logger.info(
            "maa_counsel_activate_view_get user_id=%s active_version=%s confirm_sha_prefix=%s",
            request.user.pk,
            snapshot["active_version"],
            confirm_token_sha_prefix,
        )
        return render(request, self.template_name, ctx)

    # ── POST: validate + execute activation ──────────────────────────

    def post(self, request, *args, **kwargs):
        operator_user_id = getattr(request.user, "pk", None)
        snapshot = _current_state_snapshot()

        # If already at v2.0, refuse early with an explicit message.
        if snapshot["is_v2_active"]:
            return self._render_form_error(
                request,
                kwargs,
                snapshot,
                ["MAA v2.0 is already the active version on this environment."],
                status=400,
            )

        posted = request.POST
        pdf_url = (posted.get("counsel_signoff_pdf_url") or "").strip()
        attestation_name = (posted.get("counsel_attestation_name") or "").strip()
        attestation_text = (posted.get("counsel_attestation_text") or "")
        confirm_token = (posted.get("confirm_token") or "").strip()
        typed_phrase = (posted.get("confirm_typed_phrase") or "").strip()

        errors: list[str] = []

        url_ok, url_reason = _validate_url(pdf_url)
        if not url_ok:
            errors.append(f"counsel_signoff_pdf_url: {url_reason}")
        if not attestation_name or len(attestation_name) > 256:
            errors.append("counsel_attestation_name: required, 1..256 chars.")
        if not attestation_text or len(attestation_text) > 8192:
            errors.append("counsel_attestation_text: required, 1..8192 chars.")
        # Constant-time phrase compare.
        if not hmac.compare_digest(
            typed_phrase.encode("utf-8"),
            _CONFIRM_PHRASE.encode("utf-8"),
        ):
            errors.append(
                "confirm_typed_phrase: must match the printed phrase exactly."
            )
        # Confirm-token redemption (constant-time + one-shot).
        if not _consume_token(confirm_token, operator_user_id):
            errors.append(
                "confirm_token: missing, expired, or not issued to this user."
            )

        if errors:
            logger.info(
                "maa_counsel_activate_post_validation_failed user_id=%s err_count=%d",
                operator_user_id, len(errors),
            )
            return self._render_form_error(
                request, kwargs, snapshot, errors, status=400,
                preserve_values={
                    "counsel_signoff_pdf_url": pdf_url,
                    "counsel_attestation_name": attestation_name,
                    "confirm_typed_phrase": typed_phrase,
                },
            )

        # All checks passed — execute the flip.
        from apps.migration_cloud.models_maa_state import (
            MAAActiveVersionState,
            MAAAlreadyActiveError,
        )

        try:
            MAAActiveVersionState.activate_v2(
                operator_user=request.user,
                counsel_pdf_url=pdf_url,
                attestation_name=attestation_name,
                attestation_text=attestation_text,
            )
        except MAAAlreadyActiveError:
            return self._render_form_error(
                request,
                kwargs,
                _current_state_snapshot(),
                ["MAA v2.0 is already the active version on this environment."],
                status=400,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(
                "maa_counsel_activate_flip_failed user_id=%s err_type=%s",
                operator_user_id, type(exc).__name__,
            )
            return self._render_form_error(
                request,
                kwargs,
                _current_state_snapshot(),
                [
                    "Unexpected error during activation — see operator logs. "
                    "No state was changed.",
                ],
                status=500,
            )

        # Discard raw attestation_text from memory; only the sha256
        # fingerprint lives on past this point (in the audit event +
        # model row).
        del attestation_text  # noqa: WPS420 — explicit best-effort

        messages.success(
            request,
            "MAA v2.0 activated. New signers will be bound to v2.0 going forward.",
        )
        logger.info(
            "maa_counsel_activate_flip_succeeded user_id=%s",
            operator_user_id,
        )
        # Redirect back to GET so the page refresh shows the new state
        # and a fresh confirm token (not strictly needed; defensive).
        try:
            target = reverse(
                f"migration_cloud_{kwargs.get('shell', 'super')}"
                f":maa_counsel_activate"
            )
        except NoReverseMatch:
            target = request.path
        return redirect(target)

    # ── helpers ──────────────────────────────────────────────────────

    def _render_form_error(
        self,
        request,
        kwargs: dict[str, Any],
        snapshot: dict[str, Any],
        errors: list[str],
        *,
        status: int = 400,
        preserve_values: dict[str, str] | None = None,
    ):
        confirm_plaintext, confirm_token_sha_prefix = _issue_token(
            getattr(request.user, "pk", None),
        )
        v2_full_text = ""
        try:
            v2_full_text = _render_v2_full_text()
        except Exception:  # noqa: BLE001
            pass
        back_url = "#"
        for candidate in (
            "migration_cloud_super:migration_cloud_command_center",
            "migration_cloud_portal:migration_cloud_command_center",
        ):
            try:
                back_url = reverse(candidate)
                break
            except NoReverseMatch:
                continue
        ctx = {
            "shell": kwargs.get("shell", "super"),
            "page_title": "Migration Cloud — MAA v2.0 counsel-activate",
            "state": snapshot,
            "v2_full_text": v2_full_text,
            "confirm_token": confirm_plaintext,
            "confirm_token_sha_prefix": confirm_token_sha_prefix,
            "confirm_phrase_expected": _CONFIRM_PHRASE,
            "back_url": back_url,
            "form_errors": errors,
            "form_values": preserve_values or {
                "counsel_signoff_pdf_url": "",
                "counsel_attestation_name": "",
                "confirm_typed_phrase": "",
            },
        }
        response = render(request, self.template_name, ctx, status=status)
        return response


__all__ = ["MAACounselActivateView"]
