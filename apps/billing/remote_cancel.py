"""Pluggable provider-side subscription-cancel adapter for offboarding.

The offboarding path (``apps.billing.offboarding``) must cancel a tenant's
remote (e.g. Stripe) subscription before the local row is CASCADE-deleted. The
actual provider call is an external dependency that varies by deployment, so it
is resolved at runtime from configuration rather than hardcoded — keeping the
no-hardcode contract and letting an operator wire a real cancel client WITHOUT a
code change.

Configuration (first match wins):

* Django setting ``BILLING_REMOTE_CANCEL_ADAPTER``
* env var ``RMC_BILLING_REMOTE_CANCEL_ADAPTER``

The value is a dotted path to a callable ``(external_ref: str) -> bool`` that
returns ``True`` when the provider confirmed cancellation. Example::

    RMC_BILLING_REMOTE_CANCEL_ADAPTER=myproject.billing_adapters.stripe_cancel

When no adapter is configured (the default), :func:`try_remote_cancel` is a safe
no-op returning ``False`` — the ref is recorded as ``remote_pending`` for
operator/cron reconciliation rather than silently assumed cancelled. The call is
fully guarded: a missing/broken adapter or a provider error can never raise into
the offboarding flow.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_SETTING_NAME = "BILLING_REMOTE_CANCEL_ADAPTER"
_ENV_NAME = "RMC_BILLING_REMOTE_CANCEL_ADAPTER"


def _configured_dotted_path() -> str:
    """Return the configured adapter dotted-path, or '' when unset.

    Django setting takes precedence over the env var so a deployment can pin the
    adapter declaratively; the env var is the ops-friendly override.
    """
    try:
        from django.conf import settings

        value = getattr(settings, _SETTING_NAME, None)
    except Exception:  # noqa: BLE001 - settings access must never break offboarding
        value = None
    if not value:
        value = os.environ.get(_ENV_NAME)
    return (value or "").strip()


def resolve_remote_cancel_adapter() -> Optional[Callable[[str], bool]]:
    """Resolve the configured cancel adapter callable, or ``None`` when unset.

    Resolution is per-call (not cached) so a settings override in tests or a
    runtime config change takes effect immediately; offboarding is rare enough
    that the import cost is irrelevant. A bad dotted path logs a warning and
    resolves to ``None`` (→ safe no-op) rather than raising.
    """
    dotted = _configured_dotted_path()
    if not dotted:
        return None
    try:
        from django.utils.module_loading import import_string

        adapter = import_string(dotted)
    except Exception:  # noqa: BLE001 - misconfiguration must degrade to no-op
        logger.warning(
            "billing.remote_cancel adapter %r could not be imported — "
            "falling back to no-op (refs will be recorded remote_pending)",
            dotted,
            exc_info=True,
        )
        return None
    if not callable(adapter):
        logger.warning(
            "billing.remote_cancel adapter %r is not callable — falling back to no-op",
            dotted,
        )
        return None
    return adapter


def try_remote_cancel(external_ref: str) -> bool:
    """Attempt a provider-side subscription cancel. Returns True when cancelled.

    Safe by construction: empty ref → False; no adapter configured → False;
    adapter raising → logged and False. A ``False`` return means "not confirmed
    cancelled remotely", so the caller records the ref as ``remote_pending``.
    """
    if not external_ref:
        return False
    adapter = resolve_remote_cancel_adapter()
    if adapter is None:
        return False
    try:
        return bool(adapter(external_ref))
    except Exception:  # noqa: BLE001 - a provider error must not fail the purge
        logger.warning(
            "billing.remote_cancel adapter raised cancelling ref=%s — "
            "recording remote_pending",
            external_ref,
            exc_info=True,
        )
        return False
