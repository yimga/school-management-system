"""Wave 9 Agent N (v3.58.x) — server-side vendor write-path authorization gate.

Per ``docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md``, write paths
into FACTS + Skyward (and, by extension, any vendor whose write surface
might land under counsel review) remain literal honest-stubs in
``companion-extension/src/vendors/*.ts``. This module is the
**platform-side double-gate** that any future server-side code MUST
call before invoking a vendor-mutating operation.

The gate uses the same constant-time-compare double-token pattern as
v3.39.0's audit purge command: an *approval token* AND a *counsel
signoff SHA-256* are BOTH required in the environment, and the
approval token must validate via :func:`hmac.compare_digest` against
``sha256(f"{vendor_slug}:{counsel_signoff_pdf_sha256}")``. This means:

  * the approval token is bound to a specific signoff PDF (rotate
    the PDF → the binding breaks → operator must re-approve);
  * a leaked approval token is useless without the matching
    signoff-SHA env var;
  * the gate never reads or stores the actual PDF — only the operator-
    supplied SHA-256, which is a free-form 64-hex string the operator
    computed externally with ``shasum -a 256 maa_v2_signoff.pdf``.

Future write-path call sites MUST:

    from apps.migration_cloud.services.vendor_write_gate import (
        assert_vendor_write_authorized,
        VendorWriteNotAuthorizedError,
    )

    def some_facts_write_path(...):
        assert_vendor_write_authorized("facts")   # raises if not OK
        # ...actual write...

The check is intentionally side-effect-free: no audit row is written
here (the call site is responsible for that — see
:mod:`apps.migration_cloud.models_audit`).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from typing import Final

logger = logging.getLogger(__name__)


# The full set of vendor slugs the gate recognizes. The first 4
# (PowerSchool/Blackbaud/Veracross/Alma) are *read-path* vendors; their
# *write-path* status is still subject to the same gate as a forward-
# compatibility play. The last 2 (FACTS/Skyward) are the counsel-pending
# items the docket actively tracks.
VENDOR_SLUGS: Final[tuple[str, ...]] = (
    "powerschool",
    "blackbaud",
    "veracross",
    "alma",
    "facts",
    "skyward",
)


# Vendor slugs whose write paths are *currently* blocked by counsel docket.
# Surfaced separately so the dashboard view can flag them visually.
COUNSEL_DOCKETED_VENDORS: Final[frozenset[str]] = frozenset({
    "facts",
    "skyward",
})


_APPROVAL_TOKEN_ENV_TEMPLATE = "RMC_VENDOR_WRITE_APPROVAL_TOKEN_{vendor_upper}"
_SIGNOFF_SHA_ENV_TEMPLATE = "RMC_VENDOR_WRITE_COUNSEL_SIGNOFF_SHA_{vendor_upper}"


class VendorWriteNotAuthorizedError(RuntimeError):
    """Raised by :func:`assert_vendor_write_authorized` on any refusal.

    Attributes:
        vendor_slug: the slug the gate was asked to authorize.
        reason: short stable identifier for the refusal class (one of
            ``"unknown_vendor"`` / ``"missing_approval_token"`` /
            ``"missing_counsel_signoff_sha"`` /
            ``"malformed_counsel_signoff_sha"`` /
            ``"token_mismatch"``).
    """

    def __init__(self, vendor_slug: str, reason: str) -> None:
        self.vendor_slug = vendor_slug
        self.reason = reason
        super().__init__(
            f"vendor write not authorized: vendor={vendor_slug!r} "
            f"reason={reason!r} — see docs/FACTS_SKYWARD_WRITE_PATH_FLIP_RUNBOOK.md"
        )


def _env_names(vendor_slug: str) -> tuple[str, str]:
    """Return the two env-var names for the given vendor."""
    upper = vendor_slug.upper()
    return (
        _APPROVAL_TOKEN_ENV_TEMPLATE.format(vendor_upper=upper),
        _SIGNOFF_SHA_ENV_TEMPLATE.format(vendor_upper=upper),
    )


def _is_valid_sha256_hex(value: str) -> bool:
    """Return True iff ``value`` is a 64-character lowercase hex string."""
    if not isinstance(value, str):
        return False
    if len(value) != 64:
        return False
    return bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _expected_token_hash(vendor_slug: str, counsel_sha: str) -> str:
    """Return the SHA-256 hex of ``f"{vendor_slug}:{counsel_sha}"``.

    The approval token is compared against this hash via
    :func:`hmac.compare_digest`. Operators compute the digest externally
  (stdlib only) and provision it as ``RMC_VENDOR_WRITE_APPROVAL_TOKEN_<VENDOR>``,
  e.g. ``hashlib.sha256(b"facts:<sha>").hexdigest()``.
    """
    pre = f"{vendor_slug}:{counsel_sha}".encode("utf-8")
    return hashlib.sha256(pre).hexdigest()


def is_vendor_write_authorized(vendor_slug: str) -> bool:
    """Non-raising convenience wrapper — returns True on full pass."""
    try:
        assert_vendor_write_authorized(vendor_slug)
        return True
    except VendorWriteNotAuthorizedError:
        return False


def assert_vendor_write_authorized(vendor_slug: str) -> None:
    """Raise :class:`VendorWriteNotAuthorizedError` unless all gates pass.

    Gates (in order):

      1. ``vendor_slug`` is in :data:`VENDOR_SLUGS`.
      2. ``RMC_VENDOR_WRITE_APPROVAL_TOKEN_<VENDOR>`` env var is set.
      3. ``RMC_VENDOR_WRITE_COUNSEL_SIGNOFF_SHA_<VENDOR>`` env var is
         set AND is a 64-char lowercase hex string.
      4. ``sha256(f"{vendor_slug}:{counsel_sha}")`` validates against
         the approval token via :func:`hmac.compare_digest`.

    Logging hygiene: this function NEVER logs the approval token or the
    counsel-signoff SHA. Only the vendor slug + refusal reason class.
    """
    slug = (vendor_slug or "").strip().lower()
    if slug not in VENDOR_SLUGS:
        logger.warning(
            "vendor_write_gate.unknown_vendor vendor=%s",
            slug or "(empty)",
        )
        raise VendorWriteNotAuthorizedError(slug, "unknown_vendor")

    token_env, sha_env = _env_names(slug)
    token_value = (os.environ.get(token_env, "") or "").strip()
    sha_value = (os.environ.get(sha_env, "") or "").strip().lower()

    if not token_value:
        logger.info(
            "vendor_write_gate.missing_approval_token vendor=%s",
            slug,
        )
        raise VendorWriteNotAuthorizedError(slug, "missing_approval_token")

    if not sha_value:
        logger.info(
            "vendor_write_gate.missing_counsel_signoff_sha vendor=%s",
            slug,
        )
        raise VendorWriteNotAuthorizedError(slug, "missing_counsel_signoff_sha")

    if not _is_valid_sha256_hex(sha_value):
        logger.warning(
            "vendor_write_gate.malformed_counsel_signoff_sha vendor=%s",
            slug,
        )
        raise VendorWriteNotAuthorizedError(slug, "malformed_counsel_signoff_sha")

    expected = _expected_token_hash(slug, sha_value)
    # Constant-time compare — even when lengths differ
    # compare_digest returns False in O(min(len)) without leaking.
    ok = hmac.compare_digest(
        token_value.encode("utf-8"),
        expected.encode("utf-8"),
    )
    if not ok:
        logger.info(
            "vendor_write_gate.token_mismatch vendor=%s",
            slug,
        )
        raise VendorWriteNotAuthorizedError(slug, "token_mismatch")

    # Success: log at INFO with the vendor slug only. No PII / token
    # bytes leave this function.
    logger.info("vendor_write_gate.authorized vendor=%s", slug)


def get_vendor_write_status_snapshot() -> list[dict]:
    """Return per-vendor authorization status for the operator dashboard.

    The snapshot describes posture WITHOUT exposing token bytes. Each
    row carries:

      * ``vendor_slug``
      * ``counsel_docketed`` — bool (True for facts/skyward today)
      * ``approval_token_configured`` — bool (env var set?)
      * ``counsel_signoff_sha_configured`` — bool
      * ``counsel_signoff_sha_well_formed`` — bool (64-hex shape?)
      * ``authorized`` — bool (full gate passes today?)
      * ``refusal_reason`` — None on pass; the reason class on refusal.
    """
    rows: list[dict] = []
    for slug in VENDOR_SLUGS:
        token_env, sha_env = _env_names(slug)
        token_set = bool((os.environ.get(token_env, "") or "").strip())
        sha_raw = (os.environ.get(sha_env, "") or "").strip().lower()
        sha_set = bool(sha_raw)
        sha_ok = _is_valid_sha256_hex(sha_raw) if sha_set else False
        try:
            assert_vendor_write_authorized(slug)
            authorized = True
            refusal_reason = None
        except VendorWriteNotAuthorizedError as exc:
            authorized = False
            refusal_reason = exc.reason
        rows.append(
            {
                "vendor_slug": slug,
                "counsel_docketed": slug in COUNSEL_DOCKETED_VENDORS,
                "approval_token_configured": token_set,
                "counsel_signoff_sha_configured": sha_set,
                "counsel_signoff_sha_well_formed": sha_ok,
                "authorized": authorized,
                "refusal_reason": refusal_reason,
            }
        )
    return rows


__all__ = [
    "COUNSEL_DOCKETED_VENDORS",
    "VENDOR_SLUGS",
    "VendorWriteNotAuthorizedError",
    "assert_vendor_write_authorized",
    "get_vendor_write_status_snapshot",
    "is_vendor_write_authorized",
]
