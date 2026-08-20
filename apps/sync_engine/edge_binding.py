"""Where the box's cloud coordinates come from, resolved in ONE place.

Before this, three values were read from three different places by six modules:
``RMC_EDGE_OPERATOR_BASE`` as a Django setting, ``RMC_EDGE_CREDENTIAL`` straight from
``os.getenv`` in ``sync_runner`` and again in ``connectivity_probe``, and
``RMC_EDGE_SCHOOL_SLUG`` wherever a command happened to want it. Every one of those is
a hand-edited env var living outside the container.

Everything now asks here, and here answers in a fixed order:

    1. the durable binding written by pairing (``EdgeCloudBinding``)
    2. the environment / settings, unchanged, for boxes that were never paired
    3. for the base only: a value DERIVED from the school slug

Step 3 is worth its own note. ``https://<slug>.<base-domain>`` is the only shape a
tenant host takes, so asking an operator to type the whole URL is asking them to
introduce a typo into the one value that produces the most confusing failure — under
django-tenants the Postgres schema is chosen from the hostname before authentication
runs, so a *plausible but wrong* host authenticates fine and then queries the wrong
schema. Deriving it removes the opportunity.

Every function tolerates a missing database. A box mid-migration, or a management
command run before ``migrate``, must degrade to the environment rather than crash —
these are read on the sync path, and a resolver that raises would take sync down to
report a configuration question.
"""
from __future__ import annotations

import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)


def _binding():
    """The single binding row, or None. Never raises."""
    try:
        from apps.sync_engine.models_pairing import EdgeCloudBinding

        # tenant-isolation-allow: single-row-box-local-binding-there-is-exactly-one-cloud-per-box
        return EdgeCloudBinding.objects.order_by("-updated_at").first()
    except Exception:  # noqa: BLE001 — no table yet, no DB, or app not ready
        logger.debug("edge_binding: binding lookup unavailable", exc_info=True)
        return None


def _env_base() -> str:
    base = (getattr(settings, "RMC_EDGE_OPERATOR_BASE", "") or "").strip()
    if not base:
        base = (getattr(settings, "RMC_HUB_BASE_URL", "") or "").strip()
    return base.rstrip("/")


def derive_operator_base(slug: str) -> str:
    """``https://<slug>.<base-domain>`` — the only shape a tenant host takes."""
    slug = (slug or "").strip().lower()
    if not slug:
        return ""
    domain = (
        os.getenv("MULTI_TENANT_BASE_DOMAIN", "").strip()
        or (getattr(settings, "MULTI_TENANT_BASE_DOMAIN", "") or "").strip()
        or "runmycampus.com"
    )
    # A LAN-only base domain (school.lan) would derive a host that resolves to the box
    # itself, which is never the cloud. Refuse rather than hand back a self-reference.
    if domain.endswith(".lan") or domain in ("localhost", "local"):
        return ""
    return f"https://{slug}.{domain}"


def school_slug() -> str:
    binding = _binding()
    if binding is not None and binding.school_slug:
        return binding.school_slug
    return (os.getenv("RMC_EDGE_SCHOOL_SLUG", "") or "").strip().lower()


def operator_base() -> str:
    """Cloud base URL this box syncs against. Empty when genuinely unconfigured."""
    binding = _binding()
    if binding is not None and binding.operator_base:
        return binding.operator_base.rstrip("/")
    env = _env_base()
    if env:
        return env
    return derive_operator_base(school_slug())


def edge_credential() -> str:
    """Machine bearer credential. Empty when the box is not paired."""
    binding = _binding()
    if binding is not None and binding.credential:
        return binding.credential
    return (os.getenv("RMC_EDGE_CREDENTIAL") or "").strip()


def is_paired() -> bool:
    return bool(operator_base() and edge_credential())


def is_sealed() -> bool:
    """True once this box has completed a pairing.

    Claim-on-first-boot, then seal. The anonymous pairing screen is only reachable
    while this is False; afterwards re-pairing requires an authenticated admin on the
    box or a command run on the host, either of which proves more than being on the
    LAN does.
    """
    binding = _binding()
    if binding is not None:
        return bool(binding.sealed)
    # A box configured the old way (env vars, never paired) is already bound, and
    # should not be offering an anonymous adoption screen to its LAN.
    return bool(_env_base() and (os.getenv("RMC_EDGE_CREDENTIAL") or "").strip())


def _invalidate_enabled_memo() -> None:
    """Tell :mod:`edge_enabled` its cached answer is stale. Never raises."""
    try:
        from apps.sync_engine.edge_enabled import invalidate

        invalidate()
    except Exception:  # noqa: BLE001 — a stale memo must not fail a pairing
        logger.debug("edge_binding: could not invalidate the enabled memo", exc_info=True)


def save_binding(
    *,
    operator_base: str,
    credential: str,
    school_slug: str = "",
    school_name: str = "",
    device_id: str = "",
    credential_expires_at=None,
    via: str = "pairing",
):
    """Persist the binding and seal the box. Returns the row, or None on failure."""
    from django.utils import timezone

    from apps.sync_engine.models_pairing import EdgeCloudBinding

    row = _binding()
    if row is None:
        row = EdgeCloudBinding()
    row.operator_base = (operator_base or "").strip().rstrip("/")
    row.credential = (credential or "").strip()
    row.school_slug = (school_slug or "").strip().lower()
    row.school_name = (school_name or "").strip()
    row.device_id = (device_id or "").strip()
    row.credential_expires_at = credential_expires_at
    row.paired_at = timezone.now()
    row.paired_via = via
    row.sealed = True
    row.save()
    # A paired box IS an enabled box (see edge_enabled). Bust the memo now so sync
    # starts on the next tick instead of at the next container restart — the pairing
    # screen the installer is watching is the wrong place to learn about a TTL.
    _invalidate_enabled_memo()
    logger.info(
        "edge_binding: box paired to %s as %s", row.operator_base, row.school_slug
    )
    return row


def clear_binding() -> bool:
    """Unpair. Returns True when a binding was removed.

    Deliberately does NOT touch the environment: an operator who unpairs a box that
    also has env vars set gets the env behaviour back, which is the documented
    fallback rather than a surprise.
    """
    row = _binding()
    if row is None:
        return False
    row.delete()
    _invalidate_enabled_memo()
    logger.warning("edge_binding: binding cleared; box is unpaired")
    return True


def binding_summary() -> dict:
    """Read-only view for the pairing screen and the Sync Center. Never raises."""
    binding = _binding()
    return {
        "paired": is_paired(),
        "sealed": is_sealed(),
        "operator_base": operator_base(),
        "school_slug": school_slug(),
        "school_name": getattr(binding, "school_name", "") if binding else "",
        "device_id": getattr(binding, "device_id", "") if binding else "",
        "paired_at": getattr(binding, "paired_at", None) if binding else None,
        "source": (
            "pairing" if binding is not None and binding.operator_base else "environment"
        ),
        "credential_expires_at": (
            getattr(binding, "credential_expires_at", None) if binding else None
        ),
    }


__all__ = [
    "binding_summary",
    "clear_binding",
    "derive_operator_base",
    "edge_credential",
    "is_paired",
    "is_sealed",
    "operator_base",
    "save_binding",
    "school_slug",
]
