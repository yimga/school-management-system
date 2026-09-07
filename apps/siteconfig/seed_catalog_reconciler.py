"""Desired-state diff between a DECLARED seed manifest and the ACTUAL database.

Why this module exists
----------------------
``apps/siteconfig/platform_seed_audit.py`` already answers "is the seed
complete?" with a boolean and one human sentence. It cannot answer "complete
relative to WHAT, and by how much?", and its own detail string truncates the
evidence it prints::

    f"missing {len(missing)}: {missing[:12]}"

A reader who counts the codes on that line reads *twelve* no matter what the
real number is. So a gap report that says "12 institution types missing, 12
access roles missing" is, from the console output alone, indistinguishable from
"50 missing": the display cap and the claimed figure are the same number. The
true count IS printed (``len(missing)`` comes first), but the list beside it is
not the whole list, and nothing in the output says so.

This module is the receipt half of the fix. It is a pure diff -- no Django
import, no database, no I/O -- between a declared manifest and a set of actual
natural keys, carrying:

  * the FULL, untruncated missing and extra lists,
  * a checksum of the manifest that produced them, so a receipt can be pinned
    to the exact catalog revision it was computed against, and
  * ``inactive``: declared rows that EXIST but are switched off.

That last one is not decoration. The seeders and the audit disagree about it
today: ``ensure_institution_type_registry_seed()`` short-circuits on
``InstitutionTypeRegistry.objects.count()`` (every row, active or not) while
``audit_platform_seed`` compares against ``filter(is_active=True)``. A catalog
whose rows are all present but deactivated therefore reports "missing" forever
while the seeder that would fix it believes it has nothing to do. Reporting
absent and inactive as two different states is what keeps a reconciler from
"repairing" a row that is already there.

Being import-free is a feature: this file can be unit-tested, and its numbers
reproduced, without a settings module, a migration, or a test database.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

RECEIPT_VERSION = "1"


def normalize_codes(values: Iterable[Any]) -> tuple[str, ...]:
    """Sorted, de-duplicated, whitespace-trimmed natural keys.

    Comparison is case SENSITIVE on purpose. ``BASE_SCHOOL`` and ``base_school``
    are two different rows to the database's unique index, so folding case here
    would report a catalog as in sync while every lookup by the declared code
    kept missing.
    """
    seen: dict[str, None] = {}
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            seen[text] = None
    return tuple(sorted(seen))


def manifest_checksum(codes: Iterable[Any]) -> str:
    """Order-independent fingerprint of a DECLARED manifest.

    Two receipts computed against the same manifest revision carry the same
    checksum, so "this drift was measured against the catalog as it stood at
    <sha>" is a checkable statement rather than a claim.
    """
    payload = json.dumps(
        list(normalize_codes(codes)), separators=(",", ":"), ensure_ascii=False
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CatalogDiff:
    """One catalog's declared-vs-actual comparison. Pure data; no queries."""

    key: str
    declared: tuple[str, ...]
    actual: tuple[str, ...]
    missing: tuple[str, ...]
    extra: tuple[str, ...]
    inactive: tuple[str, ...]
    checksum: str
    model_label: str = ""
    natural_key: str = "code"
    apply_supported: bool = True
    remedy: str = ""

    @property
    def declared_count(self) -> int:
        return len(self.declared)

    @property
    def actual_count(self) -> int:
        """Rows found in the database, INCLUDING ones the manifest never declared."""
        return len(self.actual)

    @property
    def present_count(self) -> int:
        """Declared rows that exist. Counted directly, not derived from
        ``declared_count - missing_count``: deriving it would make the tally
        close by construction and hide exactly the arithmetic bug a receipt is
        supposed to catch."""
        return len(set(self.declared) & set(self.actual))

    @property
    def missing_count(self) -> int:
        return len(self.missing)

    @property
    def extra_count(self) -> int:
        return len(self.extra)

    @property
    def inactive_count(self) -> int:
        return len(self.inactive)

    @property
    def in_sync(self) -> bool:
        """Every declared row exists. Extra rows do NOT make a catalog out of
        sync: a tenant-authored global role is legitimate and this reconciler
        never proposes deleting one."""
        return not self.missing

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "model": self.model_label,
            "natural_key": self.natural_key,
            "checksum": self.checksum,
            "in_sync": self.in_sync,
            "declared_count": self.declared_count,
            "present_count": self.present_count,
            "missing_count": self.missing_count,
            "extra_count": self.extra_count,
            "inactive_count": self.inactive_count,
            "actual_count": self.actual_count,
            # Full lists, never truncated. The whole point of the receipt.
            "missing": list(self.missing),
            "extra": list(self.extra),
            "inactive": list(self.inactive),
            "apply_supported": self.apply_supported,
            "remedy": self.remedy,
        }


def diff_catalog(
    key: str,
    *,
    declared: Iterable[Any],
    actual: Iterable[Any],
    inactive: Iterable[Any] = (),
    model_label: str = "",
    natural_key: str = "code",
    apply_supported: bool = True,
    remedy: str = "",
) -> CatalogDiff:
    """Compare one declared manifest against one set of actual natural keys.

    ``actual`` must be EVERY row in the catalog, active or not. ``inactive`` is
    the subset that exists but is switched off; it is intersected with the
    declared manifest, because an inactive row nobody declared is just an extra.
    """
    declared_codes = normalize_codes(declared)
    actual_codes = normalize_codes(actual)
    declared_set = set(declared_codes)
    actual_set = set(actual_codes)
    return CatalogDiff(
        key=key,
        declared=declared_codes,
        actual=actual_codes,
        missing=tuple(sorted(declared_set - actual_set)),
        extra=tuple(sorted(actual_set - declared_set)),
        inactive=tuple(sorted(declared_set & set(normalize_codes(inactive)))),
        checksum=manifest_checksum(declared_codes),
        model_label=model_label,
        natural_key=natural_key,
        apply_supported=apply_supported,
        remedy=remedy,
    )


@dataclass(frozen=True)
class ReconcileReceipt:
    """The structured result of one reconciliation pass."""

    diffs: tuple[CatalogDiff, ...]
    scope: str = "all"
    mode: str = "read-only"
    generated_at: str = ""
    created: tuple[tuple[str, tuple[str, ...]], ...] = field(default_factory=tuple)

    @property
    def manifest_checksum(self) -> str:
        """Checksum over every catalog's checksum, so one value identifies the
        whole declared surface this receipt was measured against."""
        payload = json.dumps(
            sorted((d.key, d.checksum) for d in self.diffs),
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def drifted(self) -> tuple[CatalogDiff, ...]:
        return tuple(d for d in self.diffs if not d.in_sync)

    @property
    def with_extras(self) -> tuple[CatalogDiff, ...]:
        return tuple(d for d in self.diffs if d.extra)

    def has_drift(self, *, include_extra: bool = False) -> bool:
        if self.drifted:
            return True
        return bool(include_extra and self.with_extras)

    @property
    def totals(self) -> dict[str, int]:
        return {
            "catalogs": len(self.diffs),
            "declared": sum(d.declared_count for d in self.diffs),
            "present": sum(d.present_count for d in self.diffs),
            "missing": sum(d.missing_count for d in self.diffs),
            "extra": sum(d.extra_count for d in self.diffs),
            "inactive": sum(d.inactive_count for d in self.diffs),
        }

    @property
    def created_count(self) -> int:
        return sum(len(codes) for _key, codes in self.created)

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_version": RECEIPT_VERSION,
            "generated_at": self.generated_at,
            "scope": self.scope,
            "mode": self.mode,
            "manifest_checksum": self.manifest_checksum,
            "in_sync": not self.has_drift(),
            "totals": self.totals,
            "catalogs": [d.to_dict() for d in self.diffs],
            "created": {key: list(codes) for key, codes in self.created},
            "created_count": self.created_count,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)


def build_receipt(
    diffs: Sequence[CatalogDiff],
    *,
    scope: str = "all",
    mode: str = "read-only",
    generated_at: str = "",
    created: Sequence[tuple[str, Sequence[str]]] = (),
) -> ReconcileReceipt:
    return ReconcileReceipt(
        diffs=tuple(diffs),
        scope=scope,
        mode=mode,
        generated_at=generated_at,
        created=tuple((key, tuple(codes)) for key, codes in created),
    )


__all__ = [
    "RECEIPT_VERSION",
    "CatalogDiff",
    "ReconcileReceipt",
    "build_receipt",
    "diff_catalog",
    "manifest_checksum",
    "normalize_codes",
]
