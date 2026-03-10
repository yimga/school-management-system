"""
PackageEngine: validate_package, preview_diff, apply_package, rollback (metadata plan todo 5).
Canonical format: docs/architecture/PACKAGE_FORMAT.md.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from django.db import transaction

from .models import InstalledPackage, PackageChangeLog, PackageVersion


def validate_package(payload: Dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Schema and integrity checks for a package payload.
    Returns (ok, list of error messages).
    """
    errors = []
    if not isinstance(payload, dict):
        return False, ["Payload must be a dict"]
    if not payload.get("id"):
        errors.append("Missing package id")
    if not payload.get("version"):
        errors.append("Missing package version")
    for key in ("id", "version", "scope", "compatibility", "payload_sections"):
        if key in payload and not isinstance(payload.get(key), (dict, str, type(None))) and key in ("compatibility", "payload_sections"):
            if key == "payload_sections" and not isinstance(payload.get(key), dict):
                errors.append("payload_sections must be a dict")
            elif key == "compatibility" and not isinstance(payload.get(key), dict):
                errors.append("compatibility must be a dict")
    return len(errors) == 0, errors


def preview_diff(tenant_id: Optional[Any], package_id: str, version: str, payload_sections: Dict[str, Any]) -> Dict[str, Any]:
    """
    Show changes to metadata vs current state for the tenant.
    Returns a summary dict: current_versions, proposed_changes, warnings.
    """
    current = list(
        InstalledPackage.objects.filter(package_id=package_id, school_id=tenant_id, is_active=True).values_list("version", flat=True)
    )
    return {
        "current_versions": current,
        "proposed": {"package_id": package_id, "version": version, "sections": list(payload_sections.keys())},
        "warnings": [],
    }


def apply_package(
    tenant_id: Optional[Any],
    package_id: str,
    version: str,
    payload_sections: Dict[str, Any],
    mode: str = "production",
    actor_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Write package to tenant with audit trail. Creates InstalledPackage and PackageChangeLog.
    mode: "sandbox" | "production".
    Returns dict with installed_id, rollback_token, changelog_id.
    """
    rollback_token = uuid.uuid4().hex[:32]
    with transaction.atomic():
        inst = InstalledPackage.objects.create(
            package_id=package_id,
            version=version,
            school_id=tenant_id,
            scope="tenant" if tenant_id else "platform",
            applied_by_id=actor_id,
            rollback_token=rollback_token,
        )
        log = PackageChangeLog.objects.create(
            package_id=package_id,
            version=version,
            school_id=tenant_id,
            mode=mode,
            action="apply",
            rollback_token=rollback_token,
            actor_id=actor_id,
        )
    return {"installed_id": inst.pk, "rollback_token": rollback_token, "changelog_id": log.pk}


def rollback(installed_package: InstalledPackage, actor_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Deactivate an installed package and record rollback in PackageChangeLog.
    """
    with transaction.atomic():
        installed_package.is_active = False
        installed_package.save(update_fields=["is_active"])
        log = PackageChangeLog.objects.create(
            package_id=installed_package.package_id,
            version=installed_package.version,
            school_id=installed_package.school_id,
            mode="production",
            action="rollback",
            rollback_token=installed_package.rollback_token or "",
            actor_id=actor_id,
        )
    return {"changelog_id": log.pk}


class PackageEngine:
    """Facade for package operations (validate, preview, apply, rollback)."""

    @staticmethod
    def validate_package(payload: Dict[str, Any]) -> tuple[bool, list[str]]:
        return validate_package(payload)

    @staticmethod
    def preview_diff(tenant_id: Optional[Any], package_id: str, version: str, payload_sections: Dict[str, Any]) -> Dict[str, Any]:
        return preview_diff(tenant_id, package_id, version, payload_sections)

    @staticmethod
    def apply_package(
        tenant_id: Optional[Any],
        package_id: str,
        version: str,
        payload_sections: Dict[str, Any],
        mode: str = "production",
        actor_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        return apply_package(tenant_id, package_id, version, payload_sections, mode=mode, actor_id=actor_id)

    @staticmethod
    def rollback(installed_package: InstalledPackage, actor_id: Optional[int] = None) -> Dict[str, Any]:
        return rollback(installed_package, actor_id=actor_id)
