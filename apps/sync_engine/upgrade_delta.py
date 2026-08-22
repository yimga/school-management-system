"""Subtract two manifests — the "only fetch what actually changed" half of the pipeline.

A village link is the constraint that decides this module's shape. A full checkout is
tens of megabytes; the difference between two consecutive releases is usually tens of
kilobytes of templates and one JS bundle. Sending the whole tree because the hash moved
would make the pipeline unusable exactly where it matters most.

TWO PROPERTIES WORTH NAMING.

*Content-addressed, so a re-run is free.* A file is "changed" only when its SHA-256
differs. A file that was touched, reformatted back, or rebuilt byte-identically is not in
the delta, so a rebuild of unchanged source ships nothing.

*Category-bounded, so half an upgrade is a legitimate outcome.* ``categories=`` restricts
the delta to (say) templates and static assets. That is the mode a school appliance
should run by default: new layouts land without the interpreter reloading, and anything
that needs a code swap waits for a maintenance window. The caller decides; this module
only reports honestly which files it left out and why.

DELETIONS ARE REPORTED, NEVER EXECUTED HERE. ``removed`` names files the target no longer
has. Acting on that list is the rollout manager's business, and it acts on the STAGED
tree, never on the running one.
"""
from __future__ import annotations

import logging
from typing import Iterable

from apps.sync_engine.system_manifest import ASSET_CATEGORIES, MIGRATION

logger = logging.getLogger(__name__)

_DEFAULT_MAX_FILES = 5000  # magic-number-allow: delta file-count ceiling
_DEFAULT_MAX_BYTES = 256 * 1024 * 1024  # magic-number-allow: delta byte ceiling (256 MiB)


def _limits() -> tuple[int, int]:
    from django.conf import settings

    try:
        max_files = max(1, int(getattr(settings, "RMC_OTA_DELTA_MAX_FILES", _DEFAULT_MAX_FILES)))
    except (TypeError, ValueError):
        max_files = _DEFAULT_MAX_FILES
    try:
        max_bytes = max(1, int(getattr(settings, "RMC_OTA_DELTA_MAX_BYTES", _DEFAULT_MAX_BYTES)))
    except (TypeError, ValueError):
        max_bytes = _DEFAULT_MAX_BYTES
    return max_files, max_bytes


def _files(manifest: dict) -> dict:
    files = (manifest or {}).get("files")
    return files if isinstance(files, dict) else {}


def compute_delta(
    base: dict,
    target: dict,
    *,
    categories: Iterable[str] | None = None,
    max_files: int | None = None,
    max_bytes: int | None = None,
) -> dict:
    """What ``base`` must fetch to become ``target``.

    ``base`` may be ``{}`` — a box that has never generated a manifest. That produces a
    delta containing the whole target, which is correct and is also why the caller must
    respect the caps: a first-contact box on a metered link converges over several passes
    rather than pinning the link once.

    Returns::

        {
          "base_hash", "target_hash", "complete": bool,
          "added": [entry], "changed": [entry], "removed": [path],
          "file_count", "total_bytes",
          "migrations": [ {path, app_label, migration_index} ],
          "categories": [...], "truncated": bool, "omitted_count", "omitted_bytes",
        }

    ``complete`` is the field that must never be guessed at downstream: it is True only
    when this delta, applied whole, lands the box exactly on ``target_hash``. A truncated
    or category-filtered delta sets it False, and the rollout manager refuses to stamp a
    manifest it did not fully receive.
    """
    cap_files, cap_bytes = _limits()
    cap_files = max_files if max_files is not None else cap_files
    cap_bytes = max_bytes if max_bytes is not None else cap_bytes

    wanted = set(categories) if categories else None
    base_files = _files(base)
    target_files = _files(target)

    added: list[dict] = []
    changed: list[dict] = []
    omitted_count = 0
    omitted_bytes = 0
    total_bytes = 0
    truncated = False
    filtered_out = False

    # Sorted so two runs over the same pair of manifests produce byte-identical output —
    # which is what lets a resumed transfer trust an offset it computed on a prior pass.
    for path in sorted(target_files):
        entry = target_files[path] or {}
        category = str(entry.get("category") or "")
        if wanted is not None and category not in wanted:
            filtered_out = True
            continue
        previous = base_files.get(path)
        if previous and str(previous.get("sha256") or "") == str(entry.get("sha256") or ""):
            continue

        size = int(entry.get("bytes") or 0)
        if len(added) + len(changed) >= cap_files or total_bytes + size > cap_bytes:
            truncated = True
            omitted_count += 1
            omitted_bytes += size
            continue

        record = {
            "path": path,
            "sha256": str(entry.get("sha256") or ""),
            "bytes": size,
            "category": category,
        }
        if entry.get("app_label"):
            record["app_label"] = entry["app_label"]
        if entry.get("migration_index"):
            record["migration_index"] = entry["migration_index"]
        total_bytes += size
        (changed if previous else added).append(record)

    removed = sorted(
        path for path in base_files
        if path not in target_files
        and (wanted is None or str((base_files[path] or {}).get("category") or "") in wanted)
    )

    migrations = [
        {
            "path": rec["path"],
            "app_label": rec.get("app_label", ""),
            "migration_index": rec.get("migration_index", ""),
        }
        for rec in (added + changed)
        if rec["category"] == MIGRATION
    ]

    return {
        "base_hash": str((base or {}).get("manifest_hash") or ""),
        "target_hash": str((target or {}).get("manifest_hash") or ""),
        "target_version": str((target or {}).get("version_label") or ""),
        "target_engine_commit": str((target or {}).get("engine_commit") or ""),
        "complete": not truncated and not filtered_out,
        "added": added,
        "changed": changed,
        "removed": removed,
        "file_count": len(added) + len(changed),
        "total_bytes": total_bytes,
        "migrations": sorted(migrations, key=lambda m: (m["app_label"], m["migration_index"])),
        "migration_heads": dict((target or {}).get("migration_heads") or {}),
        "categories": sorted(wanted) if wanted else [],
        "truncated": truncated,
        "omitted_count": omitted_count,
        "omitted_bytes": omitted_bytes,
    }


def asset_only_delta(base: dict, target: dict, **kwargs) -> dict:
    """The delta a box may apply without reloading its interpreter."""
    return compute_delta(base, target, categories=ASSET_CATEGORIES, **kwargs)


def requires_migration(delta: dict) -> bool:
    return bool((delta or {}).get("migrations"))


def requires_code_reload(delta: dict) -> bool:
    """True when anything outside the hot-swappable asset set is in this delta."""
    for record in list((delta or {}).get("added") or []) + list((delta or {}).get("changed") or []):
        if str(record.get("category") or "") not in ASSET_CATEGORIES:
            return True
    return False


def describe(delta: dict) -> str:
    """One operator-readable line. Empty when there is nothing to say."""
    if not delta or not delta.get("file_count") and not delta.get("removed"):
        return ""
    bits = [f"{delta.get('file_count', 0)} file(s)", f"{int(delta.get('total_bytes') or 0)} bytes"]
    if delta.get("removed"):
        bits.append(f"{len(delta['removed'])} removed")
    if delta.get("migrations"):
        bits.append(f"{len(delta['migrations'])} migration(s)")
    if delta.get("truncated"):
        bits.append(
            f"TRUNCATED — {delta.get('omitted_count', 0)} file(s) deferred to a later pass"
        )
    if delta.get("categories"):
        bits.append("categories " + ",".join(delta["categories"]))
    return "; ".join(bits)


__all__ = [
    "compute_delta",
    "asset_only_delta",
    "requires_migration",
    "requires_code_reload",
    "describe",
]
