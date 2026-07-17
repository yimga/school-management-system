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
its config is loaded.

A PSP that is not ``live`` cannot settle a payment, so it is refused — the
caller learns no money can be collected instead of receiving a placeholder
URL alongside ``{"ok": true}``. Placeholder ``mode=dev`` sessions, which keep
the tenant-side UI flow renderable before PSP contracting completes, are an
explicit opt-in via ``settings.EMBEDDED_CHECKOUT_DEV_MODE``
(``RMC_EMBEDDED_CHECKOUT_DEV_MODE=1``) or ``make_dispatcher(force_dev_mode=True)``
in tests. They report ``metadata["dispatched"] = False``.
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


def _dev_mode_enabled() -> bool:
    """Whether placeholder dev sessions are allowed.

    Off unless an operator sets ``RMC_EMBEDDED_CHECKOUT_DEV_MODE=1``. A dev
    session reports payment success while contacting no PSP, so this endpoint
    being public + unauthenticated makes the opt-in deliberate rather than
    inferred from DEBUG.
    """
    from django.conf import settings

    return bool(getattr(settings, "EMBEDDED_CHECKOUT_DEV_MODE", False))


def _dev_session(session_id: str, processor: str, psp_status: str,
                 note: str = "") -> dict[str, Any]:
    """A placeholder session that is honest about having settled nothing.

    ``create_session`` stamps ``metadata["dispatched"] = True`` for any ok
    outcome and then merges this metadata over it, so ``dispatched: False``
    here is what the caller finally sees — no PSP was contacted.
    """
    metadata: dict[str, Any] = {
        "mode": "dev", "psp_status": psp_status, "dispatched": False,
    }
    if note:
        metadata["note"] = note
    return {
        "ok": True,
        "hosted_url": _dev_hosted_url(session_id, processor),
        "metadata": metadata,
    }


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
        dev_allowed = force_dev_mode or _dev_mode_enabled()

        if force_dev_mode or row.adapter_status not in _PRODUCTION_STATUSES:
            if not dev_allowed:
                # Cannot settle, and dev sessions are off. Refuse, so the
                # kernel's fallthrough tries the next candidate and finally
                # returns ok=False -> HTTP 422. Handing back a placeholder
                # URL here would report a payment that can never arrive.
                error = (f"PSP {processor!r} status={row.adapter_status} "
                         f"is not live -- cannot settle a payment")
                logger.warning("embedded_checkout refused: %s", error)
                return {"ok": False, "error": error}
            return _dev_session(session_id, processor, row.adapter_status)

        # Live dispatch path. Each live PSP has its own session creator —
        # we look it up lazily so unconfigured PSPs don't break the import.
        live_outcome = _attempt_live_dispatch(processor, req, session_id, total_minor)
        if live_outcome is not None:
            return live_outcome

        # Adapter is live but has no session creator wired yet — the same
        # "cannot actually take the money" case as above, so it fails the
        # same way rather than dressing itself up as a success.
        if not dev_allowed:
            error = (f"PSP {processor!r} is live but has no session creator "
                     f"implemented -- cannot settle a payment")
            logger.error("embedded_checkout refused: %s", error)
            return {"ok": False, "error": error}
        return _dev_session(session_id, processor, row.adapter_status,
                            note="live creator not implemented yet")

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
