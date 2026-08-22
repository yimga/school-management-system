"""Cross-layer reconciliation for governed blueprint/pack/marketplace installs.

Apply and rollback touch several stores (installation rows, ``school.settings``
markers, ``InstalledPackage``, child packs, marketplace capability packages).
This module is the single place that audits drift and repairs it immediately
after a mutation — unless the change is only *scheduled* (future work stays in
``ConfigurationChangeRequest`` until due).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.platform_runtime.blueprint_composition import (
    _installation_sort_key,
    effective_installed_blueprint_keys,
    reconcile_blueprint_marketplace_markers,
)

_ACTIVE_BLUEPRINT_STATUSES = frozenset({"applied", "partially_applied"})
_ACTIVE_PACK_STATUSES = frozenset({"applied", "partially_applied"})


@dataclass
class InstallationDriftFinding:
    code: str
    message: str
    layer: str
    repairable: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


def _latest_pack_by_key(school) -> dict[tuple[str, str], object]:
    if school is None:
        return {}
    from apps.platform_runtime.models import PackInstallation

    latest: dict[tuple[str, str], PackInstallation] = {}
    for row in PackInstallation.objects.filter(school=school).only(
        "pk", "pack_key", "pack_type", "status", "applied_at", "created_at"
    ):
        key = (row.pack_type, row.pack_key)
        prev = latest.get(key)
        if prev is None or _installation_sort_key(row) > _installation_sort_key(prev):
            latest[key] = row
    return latest


def effective_installed_pack_keys(school) -> list[tuple[str, str]]:
    latest = _latest_pack_by_key(school)
    return sorted(
        key
        for key, row in latest.items()
        if row.status in _ACTIVE_PACK_STATUSES
    )


def audit_installation_layers(school) -> dict[str, Any]:
    """Read-only drift report for one tenant school."""
    findings: list[InstallationDriftFinding] = []
    if school is None:
        return {"ok": True, "findings": [], "finding_count": 0}

    settings = dict(getattr(school, "settings", None) or {})
    effective_blueprints = set(effective_installed_blueprint_keys(school))
    effective_packs = set(effective_installed_pack_keys(school))

    for bucket, label in (
        ("blueprint_marketplace", "blueprint marker"),
        ("local_first_blueprints", "offline blueprint marker"),
    ):
        for key in dict(settings.get(bucket) or {}):
            if key not in effective_blueprints:
                findings.append(
                    InstallationDriftFinding(
                        code="orphan_blueprint_settings_marker",
                        layer="school.settings",
                        message=(
                            f"Settings still lists {label} '{key}' but no live "
                            f"blueprint installation owns it."
                        ),
                        metadata={"bucket": bucket, "blueprint_key": key},
                    )
                )

    for pack_key in dict(settings.get("pack_installation_simulation") or {}):
        # Pack type is embedded in simulation payload when present; otherwise scan
        # all pack types for an effective owner.
        owned = any(
            pk == pack_key for (_ptype, pk) in effective_packs
        )
        if not owned:
            findings.append(
                InstallationDriftFinding(
                    code="orphan_pack_settings_marker",
                    layer="school.settings",
                    message=(
                        f"Settings still lists pack simulation '{pack_key}' "
                        "but no live pack installation owns it."
                    ),
                    metadata={"pack_key": pack_key},
                )
            )

    from apps.platform_runtime.models import BlueprintInstallation, PackInstallation

    latest_blueprints = {}
    for row in BlueprintInstallation.objects.filter(school=school).only(
        "pk", "blueprint_key", "status", "applied_at", "created_at"
    ):
        prev = latest_blueprints.get(row.blueprint_key)
        if prev is None or _installation_sort_key(row) > _installation_sort_key(prev):
            latest_blueprints[row.blueprint_key] = row

    for blueprint_key, latest in latest_blueprints.items():
        if latest.status not in {"rolled_back", "failed", "rollback_failed"}:
            continue
        stale_siblings = BlueprintInstallation.objects.filter(
            school=school,
            blueprint_key=blueprint_key,
            status__in=_ACTIVE_BLUEPRINT_STATUSES,
        ).exclude(pk=latest.pk)
        if stale_siblings.exists():
            findings.append(
                InstallationDriftFinding(
                    code="stale_blueprint_sibling_applied",
                    layer="BlueprintInstallation",
                    message=(
                        f"Blueprint '{blueprint_key}' was rolled back but "
                        f"{stale_siblings.count()} older applied row(s) remain."
                    ),
                    metadata={
                        "blueprint_key": blueprint_key,
                        "stale_ids": list(stale_siblings.values_list("pk", flat=True)),
                    },
                )
            )

    for blueprint_key in effective_blueprints:
        parent = latest_blueprints.get(blueprint_key)
        if parent is None:
            continue
        orphan_packs = PackInstallation.objects.filter(
            blueprint_installation=parent,
            status=PackInstallation.Status.APPLIED,
        )
        if parent.status not in _ACTIVE_BLUEPRINT_STATUSES and orphan_packs.exists():
            findings.append(
                InstallationDriftFinding(
                    code="orphan_child_packs_after_blueprint_retract",
                    layer="PackInstallation",
                    message=(
                        f"Blueprint '{blueprint_key}' is not active but "
                        f"{orphan_packs.count()} child pack(s) still applied."
                    ),
                    metadata={
                        "blueprint_key": blueprint_key,
                        "pack_ids": list(orphan_packs.values_list("pk", flat=True)),
                    },
                )
            )

    from apps.packages.models import InstalledPackage

    for package in InstalledPackage.objects.filter(school=school, is_active=True):
        package_id = package.package_id or ""
        if package_id.startswith("blueprint:"):
            key = package_id.split(":", 1)[1]
            if key not in effective_blueprints:
                findings.append(
                    InstallationDriftFinding(
                        code="orphan_active_blueprint_package",
                        layer="InstalledPackage",
                        message=(
                            f"Package '{package_id}' is still active without a "
                            f"live blueprint installation."
                        ),
                        metadata={"package_id": package_id},
                    )
                )
        elif ":" in package_id:
            ptype, pkey = package_id.split(":", 1)
            if (ptype, pkey) not in effective_packs:
                findings.append(
                    InstallationDriftFinding(
                        code="orphan_active_pack_package",
                        layer="InstalledPackage",
                        message=(
                            f"Package '{package_id}' is still active without a "
                            "live pack installation."
                        ),
                        metadata={"package_id": package_id},
                    )
                )

    try:
        from apps.marketplace.models import AppInstallation

        for inst in AppInstallation.objects.filter(
            school=school,
            uninstalled_at__isnull=False,
        ).exclude(config={}):
            cfg = dict(inst.config or {})
            for pid in cfg.get("capability_packages_applied") or []:
                active_pkg = InstalledPackage.objects.filter(
                    school=school, package_id=pid, is_active=True
                ).exists()
                if active_pkg:
                    findings.append(
                        InstallationDriftFinding(
                            code="marketplace_uninstall_left_package",
                            layer="marketplace",
                            message=(
                                f"Uninstalled app '{inst.app.slug}' still has active "
                                f"capability package '{pid}'."
                            ),
                            metadata={
                                "app_slug": inst.app.slug,
                                "package_id": pid,
                                "installation_id": inst.pk,
                            },
                        )
                    )
    except ImportError:
        pass

    serialized = [
        {
            "code": f.code,
            "message": f.message,
            "layer": f.layer,
            "repairable": f.repairable,
            "metadata": f.metadata,
        }
        for f in findings
    ]
    return {
        "ok": len(findings) == 0,
        "findings": serialized,
        "finding_count": len(findings),
        "school_id": str(getattr(school, "pk", "") or ""),
    }


def _repair_stale_blueprint_siblings(school, *, blueprint_key: str) -> int:
    from apps.platform_runtime.models import BlueprintInstallation

    latest = (
        BlueprintInstallation.objects.filter(school=school, blueprint_key=blueprint_key)
        .order_by("-applied_at", "-id")
        .first()
    )
    if latest is None or latest.status in _ACTIVE_BLUEPRINT_STATUSES:
        return 0
    return BlueprintInstallation.objects.filter(
        school=school,
        blueprint_key=blueprint_key,
        status__in=_ACTIVE_BLUEPRINT_STATUSES,
    ).exclude(pk=latest.pk).update(
        status=BlueprintInstallation.Status.ROLLED_BACK,
        updated_at=timezone.now(),
    )


def _repair_orphan_child_packs(school, *, blueprint_installation_id: int) -> int:
    from apps.platform_runtime.pack_rollback import rollback_pack_installation
    from apps.platform_runtime.models import PackInstallation

    repaired = 0
    for pack_installation in PackInstallation.objects.filter(
        blueprint_installation_id=blueprint_installation_id,
        status=PackInstallation.Status.APPLIED,
    ):
        result = rollback_pack_installation(
            pack_installation, actor=None, confirmed=True
        )
        if result.get("ok"):
            repaired += 1
    return repaired


def _repair_orphan_packages(school, package_id: str) -> bool:
    from apps.packages.engine import rollback as rollback_package
    from apps.packages.models import InstalledPackage

    installed = (
        InstalledPackage.objects.filter(
            school=school, package_id=package_id, is_active=True
        )
        .order_by("-applied_at")
        .first()
    )
    if installed is None:
        return False
    rollback_package(installed, actor_id=None)
    return True


def reconcile_school_installations(
    school,
    *,
    repair: bool = False,
    context: str = "",
) -> dict[str, Any]:
    """Audit and optionally repair installation-layer drift for one school."""
    report = audit_installation_layers(school)
    if not repair or not report["findings"]:
        report["repaired"] = []
        report["context"] = context
        return report

    repaired: list[str] = []
    with transaction.atomic():
        removed_markers = reconcile_blueprint_marketplace_markers(school)
        if removed_markers:
            repaired.append(f"blueprint_markers:{','.join(removed_markers)}")

        for finding in report["findings"]:
            code = finding["code"]
            meta = finding.get("metadata") or {}
            if code == "stale_blueprint_sibling_applied":
                count = _repair_stale_blueprint_siblings(
                    school, blueprint_key=meta["blueprint_key"]
                )
                if count:
                    repaired.append(f"stale_blueprint_siblings:{meta['blueprint_key']}:{count}")
            elif code == "orphan_child_packs_after_blueprint_retract":
                from apps.platform_runtime.models import BlueprintInstallation

                parent = (
                    BlueprintInstallation.objects.filter(
                        school=school, blueprint_key=meta["blueprint_key"]
                    )
                    .order_by("-applied_at", "-id")
                    .first()
                )
                if parent is not None:
                    count = _repair_orphan_child_packs(
                        school, blueprint_installation_id=parent.pk
                    )
                    if count:
                        repaired.append(
                            f"orphan_child_packs:{meta['blueprint_key']}:{count}"
                        )
            elif code in {
                "orphan_active_blueprint_package",
                "orphan_active_pack_package",
                "marketplace_uninstall_left_package",
            }:
                pid = meta.get("package_id")
                if pid and _repair_orphan_packages(school, pid):
                    repaired.append(f"package_rollback:{pid}")
            elif code == "orphan_pack_settings_marker":
                settings = dict(school.settings or {})
                simulations = dict(settings.get("pack_installation_simulation") or {})
                pack_key = meta.get("pack_key")
                if pack_key and pack_key in simulations:
                    del simulations[pack_key]
                    settings["pack_installation_simulation"] = simulations
                    if not simulations:
                        settings.pop("pack_installation_simulation", None)
                    school.settings = settings
                    school.save(update_fields=["settings"])
                    repaired.append(f"pack_marker:{pack_key}")

        school.refresh_from_db()

    follow_up = audit_installation_layers(school)
    return {
        **follow_up,
        "repaired": repaired,
        "context": context,
        "pre_repair_finding_count": report["finding_count"],
    }


def finalize_installation_mutation(
    school,
    *,
    context: str,
    actor=None,
) -> dict[str, Any]:
    """Run immediately after apply/rollback/deactivate (not for schedule-only)."""
    from apps.platform_runtime.events import emit_platform_event

    result = reconcile_school_installations(school, repair=True, context=context)
    if result.get("finding_count") or result.get("repaired"):
        emit_platform_event(
            "installation_layers_reconciled",
            {
                "context": context,
                "actor_id": getattr(actor, "pk", None),
                "finding_count": result.get("finding_count", 0),
                "pre_repair_finding_count": result.get("pre_repair_finding_count", 0),
                "repaired": result.get("repaired", []),
            },
            tenant_id=str(getattr(school, "pk", "") or "") or None,
            school_id=str(getattr(school, "pk", "") or "") or None,
        )
    return result
