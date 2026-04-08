"""Owner-filter helpers for RuntimeDefaults sync and backfill flows."""

from __future__ import annotations

from typing import Final

from apps.siteconfig.domain_ownership import OWNERSHIP_DOMAINS

# ``delete`` is row metadata on the slim SiteSettings singleton, not a payload owner.
NON_PAYLOAD_SYNC_OWNERS: Final[frozenset[str]] = frozenset({"delete"})
RUNTIME_SYNC_OWNER_CHOICES: Final[tuple[str, ...]] = tuple(
    owner for owner in OWNERSHIP_DOMAINS if owner not in NON_PAYLOAD_SYNC_OWNERS
)


def normalize_runtime_sync_owner_filters(
    owners: list[str] | tuple[str, ...] | set[str] | None,
    exclude_owners: list[str] | tuple[str, ...] | set[str] | None,
) -> tuple[tuple[str, ...] | None, tuple[str, ...] | None]:
    """Normalize include/exclude filters and reject non-payload owner buckets."""
    normalized_owners = tuple(dict.fromkeys(owners or ())) or None
    normalized_exclude = tuple(dict.fromkeys(exclude_owners or ())) or None

    overlap = sorted(set(normalized_owners or ()) & set(normalized_exclude or ()))
    if overlap:
        raise ValueError(
            "Owner filters overlap between --owner and --exclude-owner: "
            + ", ".join(overlap)
        )
    unknown = sorted(
        (
            set(normalized_owners or ())
            | set(normalized_exclude or ())
        )
        - set(OWNERSHIP_DOMAINS)
    )
    if unknown:
        raise ValueError(
            "RuntimeDefaults sync received unknown owners: " + ", ".join(unknown)
        )

    non_payload = sorted(
        (set(normalized_owners or ()) | set(normalized_exclude or ()))
        & NON_PAYLOAD_SYNC_OWNERS
    )
    if non_payload:
        raise ValueError(
            "RuntimeDefaults sync does not support non-payload owners: "
            + ", ".join(non_payload)
        )
    if not resolve_runtime_sync_owner_scope(normalized_owners, normalized_exclude):
        raise ValueError(
            "RuntimeDefaults sync owner filters exclude every syncable owner."
        )

    return normalized_owners, normalized_exclude


def resolve_runtime_sync_owner_scope(
    owners: tuple[str, ...] | None,
    exclude_owners: tuple[str, ...] | None,
) -> tuple[str, ...]:
    """Return the effective owner scope after include/exclude normalization."""
    excluded = set(exclude_owners or ())
    base_scope = owners if owners is not None else RUNTIME_SYNC_OWNER_CHOICES
    return tuple(owner for owner in base_scope if owner not in excluded)
