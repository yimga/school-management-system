"""Pre-flight capacity + cross-bundle validation gates.

Block obviously broken bundles BEFORE the apply step burns workers:

    * :func:`check_capacity` — bundle size vs the tenant's plan limits
      (storage, row count, student cap). Fails fast when a 50k-row bundle
      lands on a 1k-row plan tier.

    * :func:`check_cross_bundle_fks` — FK references that span bundles
      (homeroom IDs in classes.csv from bundle A referenced by students.csv
      in bundle B). Walks the MigrationIdMapping audit table to verify
      every legacy_id referenced in the candidate bundle resolves.

    * :func:`check_disk_space` — local disk has room for the intake +
      asset pipeline (rough estimate using artifact byte_size + 2× headroom).

    * :func:`check_edge_reachability` — on an EDGE appliance, whether this
      bundle writes to models the sync rail does not carry, i.e. rows that will
      stay on the box forever. It is a WARNING, not a blocker: the check passes
      unless the deployment's policy is ``refuse`` and nobody has acknowledged
      the stranding. The load-bearing copy of this guard is in the orchestrator
      (every entry path reaches it); this one exists so the wizard can show the
      operator the answer before they press the button.

    * :func:`check_catalog_routing` — spreadsheet catalog shape vs assigned
      record type (Matières vs Filières). Warning-only; surfaces on Review &
      Import via :mod:`catalog_preflight`.

    * :func:`run_all` — convenience wrapper returning a single dict
      consumed by the wizard before flipping APPLYING.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings

from .models import MigrationBundle, MigrationIdMapping

logger = logging.getLogger(__name__)


@dataclass
class PreflightCheck:
    name: str
    passed: bool
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreflightReport:
    bundle_id: int
    checks: list[PreflightCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failed(self) -> list[PreflightCheck]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "ok": self.ok,
            "checks": [
                {"name": c.name, "passed": c.passed, "message": c.message, "detail": c.detail}
                for c in self.checks
            ],
        }


_FALLBACK_PLAN_LIMITS = {
    "small": {"max_students": 1_500, "max_bytes": 500 * 1024 * 1024, "max_rows": 250_000},
    "mid": {"max_students": 15_000, "max_bytes": 5 * 1024 * 1024 * 1024, "max_rows": 5_000_000},
    "large": {"max_students": 75_000, "max_bytes": 25 * 1024 * 1024 * 1024, "max_rows": 50_000_000},
    "state": {"max_students": 1_000_000, "max_bytes": 250 * 1024 * 1024 * 1024, "max_rows": 1_000_000_000},
}


def _plan_limits(tier: str) -> dict[str, int]:
    """Resolve plan limits via the configurability cascade, with fallback."""
    from apps.migration_cloud import defaults as _mc_defaults
    try:
        all_caps = _mc_defaults.get("migration_cloud.preflight.capacity")
        return all_caps.get(tier) or _FALLBACK_PLAN_LIMITS.get(tier, _FALLBACK_PLAN_LIMITS["small"])
    except Exception:  # noqa: BLE001
        return _FALLBACK_PLAN_LIMITS.get(tier, _FALLBACK_PLAN_LIMITS["small"])


def check_capacity(*, bundle: MigrationBundle) -> PreflightCheck:
    """Compare bundle byte size + estimated row count against the tenant's plan limits."""
    artifacts = list(bundle.artifacts.all())
    total_bytes = sum(a.byte_size for a in artifacts)
    total_rows = sum((a.row_count or 0) for a in artifacts)
    student_artifacts = [a for a in artifacts if (a.inferred_source or "") and "student" in (a.path_within_bundle or "").lower()]
    student_rows = sum((a.row_count or 0) for a in student_artifacts) or total_rows
    tier = bundle.sla_tier
    limits = _plan_limits(tier)
    violations: list[str] = []
    if total_bytes > limits["max_bytes"]:
        violations.append(f"bytes {total_bytes:,} > {limits['max_bytes']:,}")
    if total_rows > limits["max_rows"]:
        violations.append(f"rows {total_rows:,} > {limits['max_rows']:,}")
    if student_rows > limits["max_students"]:
        violations.append(f"students {student_rows:,} > {limits['max_students']:,}")
    if violations:
        return PreflightCheck(
            name="capacity",
            passed=False,
            message=f"Bundle exceeds {tier} plan limits: {', '.join(violations)}",
            detail={
                "tier": tier,
                "total_bytes": total_bytes,
                "total_rows": total_rows,
                "student_rows": student_rows,
                "limits": limits,
            },
        )
    return PreflightCheck(
        name="capacity",
        passed=True,
        message=f"Within {tier} plan limits ({total_bytes:,} bytes, {total_rows:,} rows).",
        detail={"tier": tier, "limits": limits},
    )


def check_disk_space(*, bundle: MigrationBundle) -> PreflightCheck:
    """Verify there's enough free disk to hold artifacts + assets + headroom."""
    artifacts = list(bundle.artifacts.all())
    needed = sum(a.byte_size for a in artifacts) * 3  # raw + decompressed + assets headroom
    media_root = Path(getattr(settings, "MEDIA_ROOT", "media"))
    media_root.mkdir(parents=True, exist_ok=True)
    try:
        free = shutil.disk_usage(media_root).free
    except Exception:  # noqa: BLE001
        return PreflightCheck(
            name="disk_space", passed=True,
            message="Skipped: could not stat disk usage.",
        )
    passed = free >= needed
    return PreflightCheck(
        name="disk_space",
        passed=passed,
        message=(
            f"{free:,} bytes free, {needed:,} bytes estimated needed."
            if passed
            else f"Insufficient disk: {free:,} bytes free, need ~{needed:,}."
        ),
        detail={"free_bytes": free, "needed_bytes": needed},
    )


def check_cross_bundle_fks(*, bundle: MigrationBundle, namespaces: list[str] | None = None) -> PreflightCheck:
    """Walk the MigrationIdMapping audit table to verify cross-bundle legacy refs resolve.

    Heuristic: any column ending in ``_external_id`` in this bundle's mappings
    that isn't ``student_external_id`` (resolved within wave-1) is considered
    a cross-bundle reference. We sample up to N rows per artifact and check
    each referenced legacy_id has a matching MigrationIdMapping row for the
    tenant.
    """
    namespaces = namespaces or []
    per_artifact_mappings = (bundle.mapping_summary or {}).get("per_artifact") or {}
    unresolved: list[str] = []
    checked = 0
    for path, mappings in per_artifact_mappings.items():
        for m in mappings or []:
            canonical = str(m.get("canonical_field") or "")
            if not canonical.endswith("_external_id") or canonical == "student_external_id":
                continue
            samples = m.get("sample_values") or []
            for raw in samples[:5]:
                legacy_id = str(raw).strip()
                if not legacy_id:
                    continue
                checked += 1
                qs = MigrationIdMapping.objects.filter(
                    school=bundle.school, legacy_id=legacy_id,
                )
                if namespaces:
                    qs = qs.filter(legacy_namespace__in=namespaces)
                if not qs.exists():
                    unresolved.append(f"{path}:{canonical}:{legacy_id}")
                    if len(unresolved) >= 25:
                        break
            if len(unresolved) >= 25:
                break
        if len(unresolved) >= 25:
            break
    if unresolved:
        return PreflightCheck(
            name="cross_bundle_fks",
            passed=False,
            message=f"{len(unresolved)} cross-bundle FK reference(s) do not resolve to any prior bundle's ID map.",
            detail={"unresolved": unresolved[:25], "checked": checked},
        )
    return PreflightCheck(
        name="cross_bundle_fks",
        passed=True,
        message=f"All {checked} cross-bundle FK reference(s) resolve.",
        detail={"checked": checked},
    )


def check_edge_reachability(*, bundle: MigrationBundle) -> PreflightCheck:
    """On an appliance: which of this import can never leave the box.

    PASSES while warning. That reads oddly for a preflight check and is the point:
    a box owning a domain is a legitimate deliberate choice, so this must not become
    a thing operators learn to click past. It fails only under the ``refuse`` policy
    with the stranding unacknowledged -- the deployment having said, in advance, that
    it does not accept box-only data.

    On a cloud deployment, and when the policy is off, it reports the honest no-op:
    nothing here is stranded, because the cloud is where things were going.
    """
    from .edge_reachability import (
        POLICY_OFF,
        POLICY_REFUSE,
        preview_for_bundle,
    )

    report = preview_for_bundle(bundle)
    if not report.is_edge:
        return PreflightCheck(
            name="edge_reachability",
            passed=True,
            message="Not an edge appliance — every domain reaches the cloud by definition.",
            detail={"is_edge": False},
        )
    if report.policy == POLICY_OFF:
        return PreflightCheck(
            name="edge_reachability",
            passed=True,
            message="Stranded-write assessment is switched off on this deployment.",
            detail={"policy": POLICY_OFF},
        )
    if report.rail_unavailable:
        # NOT a pass dressed as one. The check could not run; say which it is.
        return PreflightCheck(
            name="edge_reachability",
            passed=True,
            message=(
                "The sync rail could not be read on this box, so no stranded-write "
                "assessment was possible. This is a check that did not run, not a "
                "clean result."
            ),
            detail={"rail_unavailable": True},
        )
    if not report.has_finding:
        return PreflightCheck(
            name="edge_reachability",
            passed=True,
            message="Every model this import writes is carried by the sync rail.",
            detail={"is_edge": True, "policy": report.policy},
        )

    blocking = report.policy == POLICY_REFUSE and not report.acknowledged
    return PreflightCheck(
        name="edge_reachability",
        passed=not blocking,
        message=report.operator_message(),
        detail=report.to_dict(),
    )


def check_catalog_routing(*, bundle: MigrationBundle) -> PreflightCheck:
    """Warn when spreadsheet catalog shape disagrees with assigned record type."""
    from .catalog_preflight import catalog_preflight_report

    report = catalog_preflight_report(bundle)
    if not report.get("has_findings"):
        return PreflightCheck(
            name="catalog_routing",
            passed=True,
            message="Subject/specialty catalog tags match file shape.",
            detail=report,
        )
    parts: list[str] = []
    for row in report.get("artifacts") or []:
        fname = row.get("filename") or "file"
        msgs = row.get("messages") or []
        if msgs:
            prefix = "CRITICAL" if row.get("severity") == "critical" else "warn"
            parts.append(f"{prefix} {fname}: {msgs[0]}")
    for msg in report.get("bundle_warnings") or []:
        parts.append(str(msg))
    return PreflightCheck(
        name="catalog_routing",
        passed=not report.get("blocking"),
        message="; ".join(parts[:4]) if parts else "Catalog routing review recommended.",
        detail=report,
    )


def run_all(*, bundle: MigrationBundle) -> PreflightReport:
    """Run every check; returns a single report consumable by the wizard."""
    return PreflightReport(
        bundle_id=bundle.pk,
        checks=[
            check_capacity(bundle=bundle),
            check_disk_space(bundle=bundle),
            check_cross_bundle_fks(bundle=bundle),
            check_edge_reachability(bundle=bundle),
            check_catalog_routing(bundle=bundle),
        ],
    )
