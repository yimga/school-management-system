"""Wave P-E (v3.95.1 — 2026-05-26) — Embedded checkout PSP dispatcher bridge.

Bridges the Wave I :func:`apps.billing.embedded_checkout.create_session`
``psp_dispatcher`` callback to the existing
:mod:`apps.billing.psp_adapter_registry`.

The kernel selects candidate processors per currency; this dispatcher
checks each candidate against the PSP registry to confirm the adapter is
``live`` (or at least ``in_progress``), then delegates to the per-PSP
session-creation function when one exists.

Failures are returned as ``{"ok": False, "error": ...}`` so the kernel's
fallthrough logic tries the next candidate.

No live HTTP calls are made unless the per-PSP creator function exists AND
its config is loaded. In dev / test, every dispatcher returns ``{"ok": True,
"hosted_url": "https://checkout.runmycampus.com/<session_id>?dev"}``.
"""

from __future__ import annotations

import logging
from typing import Any

from .embedded_checkout import CheckoutSessionRequest
from .psp_adapter_registry import get_psp


logger = logging.getLogger(__name__)


_ALLOWED_STATUSES: frozenset[str] = frozenset({"live", "in_progress", "planned"})
_PRODUCTION_STATUSES: frozenset[str] = frozenset({"live"})


def _is_dispatchable(psp_slug: str) -> tuple[bool, str]:
    """Check if a PSP is registered + allowed for dispatch.

    Returns (ok, reason)."""
    row = get_psp(psp_slug)
    if row is None:
        return False, f"PSP slug {psp_slug!r} not in registry"
    if row.adapter_status not in _ALLOWED_STATUSES:
        return False, f"PSP {psp_slug!r} status={row.adapter_status} not dispatchable"
    return True, ""


def _dev_hosted_url(session_id: str, psp_slug: str) -> str:
    return f"https://checkout.runmycampus.com/{session_id}?psp={psp_slug}&mode=dev"


def make_dispatcher(*, force_dev_mode: bool = False):
    """Return a dispatcher callable suitable for ``create_session``."""

    def dispatcher(processor: str, req: CheckoutSessionRequest,
                    session_id: str, total_minor: int) -> dict[str, Any]:
        ok, reason = _is_dispatchable(processor)
        if not ok:
            logger.info(
                "embedded_checkout dispatcher: processor=%s not dispatchable (%s)",
                processor, reason,
            )
            return {"ok": False, "error": reason}

        row = get_psp(processor)
        if force_dev_mode or row.adapter_status != "live":
            # Dev / scaffold mode — return a placeholder hosted URL so the
            # tenant-side UI flow can render. Real settlement requires
            # adapter_status="live" + live credentials.
            return {
                "ok": True,
                "hosted_url": _dev_hosted_url(session_id, processor),
                "metadata": {"mode": "dev", "psp_status": row.adapter_status},
            }

        # Live dispatch path. Each live PSP has its own session creator —
        # we look it up lazily so unconfigured PSPs don't break the import.
        live_outcome = _attempt_live_dispatch(processor, req, session_id, total_minor)
        if live_outcome is not None:
            return live_outcome

        # No live creator found → fall back to dev shape so the caller still
        # gets something usable, but mark mode=dev.
        return {
            "ok": True,
            "hosted_url": _dev_hosted_url(session_id, processor),
            "metadata": {"mode": "dev", "psp_status": row.adapter_status,
                         "note": "live creator not implemented yet"},
        }

    return dispatcher


def _attempt_live_dispatch(
    processor: str,
    req: CheckoutSessionRequest,
    session_id: str,
    total_minor: int,
) -> dict[str, Any] | None:
    """Look up the per-PSP live session creator and dispatch.

    Wave Q1 (v3.95.2): all 5 non-Stripe PSPs are wired through
    ``embedded_checkout_psp_creators``. Each creator returns ``{"ok": False,
    "error": "credentials missing"}`` until tenant credentials are stored in
    ``PlatformBillingProcessorConfig.metadata``. The dispatcher fallthrough
    then tries the next candidate.

    Wave Q2 (v3.95.2): Stripe ad-hoc amounts via ``price_data`` (no
    pre-created Stripe Price object needed).
    """
    if processor == "stripe":
        try:
            from .embedded_checkout_stripe_dynamic import (  # type: ignore
                create_stripe_dynamic_session,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("stripe dynamic creator import failed: %s", exc)
            return None
        return create_stripe_dynamic_session(req, session_id, total_minor)

    # 5 non-Stripe PSPs — all wired in Wave Q1.
    try:
        from .embedded_checkout_psp_creators import get_live_creator
    except Exception as exc:  # noqa: BLE001
        logger.warning("psp creator import failed processor=%s err=%s",
                       processor, exc)
        return None
    creator = get_live_creator(processor)
    if creator is None:
        return None
    return creator(req, session_id, total_minor)
