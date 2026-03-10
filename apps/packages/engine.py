"""
PackageEngine: validate_package, preview_diff, apply_package, rollback, promote_package.
Canonical format: docs/architecture/PACKAGE_FORMAT.md.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from django.db import transaction

from apps.metadata.services import get_downstream_dependencies

from .models import InstalledPackage, PackageChangeLog, PackageVersion


def _normalize_dependencies(raw_dependencies: Any) -> list[str]:
    if raw_dependencies in (None, ""):
        return []
    if not isinstance(raw_dependencies, list):
        raise ValueError("dependencies must be a list")
    normalized: list[str] = []
    for item in raw_dependencies:
        if isinstance(item, str):
            dep = item.strip()
        elif isinstance(item, dict):
            dep = str(item.get("package_id") or item.get("id") or "").strip()
        else:
            raise ValueError("dependencies entries must be strings or dicts")
        if dep:
            normalized.append(dep)
    return list(dict.fromkeys(normalized))


def _infer_package_type(payload_sections: dict[str, Any]) -> str:
    if not payload_sections:
        return "blueprint"
    section = next(iter(payload_sections.keys()))
    return section if section in {"blueprint", "workflow", "dashboard", "policy", "theme"} else "blueprint"


def _entity_codes_from_payload(section_payload: Any) -> set[str]:
    entity_codes: set[str] = set()
    if isinstance(section_payload, dict):
        explicit_code = str(section_payload.get("entity_code") or "").strip()
        if explicit_code:
            entity_codes.add(explicit_code)
        explicit_codes = section_payload.get("entity_codes")
        if isinstance(explicit_codes, list):
            entity_codes.update(str(code).strip() for code in explicit_codes if str(code).strip())
        entities = section_payload.get("entities")
        if isinstance(entities, list):
            for entity in entities:
                if isinstance(entity, dict):
                    code = str(entity.get("code") or entity.get("entity_code") or "").strip()
                    if code:
                        entity_codes.add(code)
        for value in section_payload.values():
            entity_codes.update(_entity_codes_from_payload(value))
    elif isinstance(section_payload, list):
        for item in section_payload:
            entity_codes.update(_entity_codes_from_payload(item))
    return entity_codes


def _artifact_codes(section_payload: Any) -> list[str]:
    codes: list[str] = []
    if isinstance(section_payload, dict):
        if section_payload.get("code"):
            codes.append(str(section_payload["code"]).strip())
        for key, value in section_payload.items():
            if key in {"layouts", "workflows", "dashboards", "policies", "templates", "apis"} and isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and item.get("code"):
                        codes.append(str(item["code"]).strip())
                    elif isinstance(item, str):
                        codes.append(item.strip())
            elif isinstance(value, dict):
                codes.extend(_artifact_codes(value))
            elif isinstance(value, list):
                codes.extend(_artifact_codes(value))
    elif isinstance(section_payload, list):
        for item in section_payload:
            codes.extend(_artifact_codes(item))
    return [code for code in codes if code]


def _field_names_from_payload(section_payload: Any) -> list[str]:
    field_names: list[str] = []
    if not isinstance(section_payload, dict):
        return field_names
    single = str(section_payload.get("field_name") or "").strip()
    if single:
        field_names.append(single)
    many = section_payload.get("field_names")
    if isinstance(many, list):
        field_names.extend(str(item).strip() for item in many if str(item).strip())
    fields = section_payload.get("fields")
    if isinstance(fields, list):
        for item in fields:
            if isinstance(item, str) and item.strip():
                field_names.append(item.strip())
            elif isinstance(item, dict):
                candidate = str(item.get("field_name") or item.get("name") or "").strip()
                if candidate:
                    field_names.append(candidate)
    return list(dict.fromkeys(field_names))


def _consumer_type_for_key(key: str | None) -> str | None:
    if not key:
        return None
    mapping = {
        "workflow": "workflow",
        "workflows": "workflow",
        "dashboard": "dashboard",
        "dashboards": "dashboard",
        "policy": "policy",
        "policies": "policy",
        "api": "api",
        "apis": "api",
        "template": "template",
        "templates": "template",
        "layout": "template",
        "layouts": "template",
        "theme": "template",
    }
    return mapping.get(str(key).strip().lower())


def _metadata_consumer_code(consumer_type: str, raw_code: str) -> str:
    return raw_code if ":" in raw_code else f"{consumer_type}:{raw_code}"


def _collect_metadata_usages(payload_sections: dict[str, Any], package_id: str) -> list[dict[str, str]]:
    refs: set[tuple[str, str, str, str]] = set()

    def walk(node: Any, key_hint: str | None = None, consumer_type: str | None = None, consumer_code: str | None = None) -> None:
        if isinstance(node, dict):
            local_consumer_type = _consumer_type_for_key(key_hint) or consumer_type
            raw_code = str(node.get("code") or node.get("slug") or consumer_code or package_id).strip()
            entity_codes = sorted(_entity_codes_from_payload(node))
            field_names = _field_names_from_payload(node)
            if local_consumer_type and raw_code and entity_codes and field_names:
                normalized_code = _metadata_consumer_code(local_consumer_type, raw_code)
                for entity_code in entity_codes:
                    for field_name in field_names:
                        refs.add((local_consumer_type, normalized_code, entity_code, field_name))
                        refs.add(("other", f"package:{package_id}", entity_code, field_name))
            for child_key, child_value in node.items():
                if isinstance(child_value, (dict, list)):
                    walk(child_value, child_key, local_consumer_type, raw_code or consumer_code)
        elif isinstance(node, list):
            for item in node:
                walk(item, key_hint, consumer_type, consumer_code)

    for section, section_payload in payload_sections.items():
        walk(section_payload, section)

    return [
        {
            "consumer_type": consumer_type,
            "consumer_code": consumer_code,
            "entity_code": entity_code,
            "field_name": field_name,
        }
        for consumer_type, consumer_code, entity_code, field_name in sorted(refs)
    ]


def _register_metadata_usages(usages: list[dict[str, str]]) -> None:
    if not usages:
        return
    from apps.metadata.usage_registry import register_usage

    for usage in usages:
        register_usage(
            usage["consumer_type"],
            usage["consumer_code"],
            usage["entity_code"],
            usage["field_name"],
        )


def _build_impact_summary(payload_sections: dict[str, Any]) -> dict[str, Any]:
    impacted = {
        "sections": list(payload_sections.keys()),
        "entity_codes": [],
        "dependencies": [],
        "artifact_codes": {},
        "runtime_recompile_required": bool(payload_sections),
    }
    entity_codes: set[str] = set()
    for section, section_payload in payload_sections.items():
        entity_codes.update(_entity_codes_from_payload(section_payload))
        codes = sorted(set(_artifact_codes(section_payload)))
        if codes:
            impacted["artifact_codes"][section] = codes
    impacted["entity_codes"] = sorted(entity_codes)
    dependencies: list[dict[str, Any]] = []
    for code in impacted["entity_codes"]:
        dependencies.extend(get_downstream_dependencies(entity_code=code))
    impacted["dependencies"] = dependencies
    return impacted


def _compatibility_report(
    tenant_id: Optional[Any],
    scope: str,
    compatibility: dict[str, Any],
    dependencies: list[str],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    school = None
    if tenant_id:
        from apps.schools.models import School

        school = School.objects.filter(pk=tenant_id).select_related("default_region", "plan").first()
        if not school:
            errors.append("Tenant not found for package preview/apply")

    allowed_scopes = compatibility.get("allowed_scopes") or []
    if allowed_scopes and scope not in allowed_scopes:
        errors.append(f"Package scope '{scope}' is not allowed by compatibility policy")

    allowed_regions = compatibility.get("allowed_regions") or []
    if school and allowed_regions:
        region_code = getattr(getattr(school, "default_region", None), "code", None) or getattr(school, "default_region_id", None)
        if region_code and region_code not in allowed_regions:
            errors.append(f"School region '{region_code}' is not in package allowed_regions")

    required_plan_slugs = compatibility.get("required_plan_slugs") or []
    if school and required_plan_slugs:
        plan_slug = getattr(getattr(school, "plan", None), "slug", "") or ""
        if plan_slug not in required_plan_slugs:
            errors.append(f"School plan '{plan_slug or 'none'}' is not compatible with this package")

    if dependencies:
        missing_dependencies = []
        existing_installs = set(
            InstalledPackage.objects.filter(
                package_id__in=dependencies,
                school_id=tenant_id,
                is_active=True,
            ).values_list("package_id", flat=True)
        )
        for dependency in dependencies:
            if dependency not in existing_installs:
                missing_dependencies.append(dependency)
        if missing_dependencies:
            errors.append(f"Missing package dependencies: {', '.join(missing_dependencies)}")

    min_platform_version = str(compatibility.get("min_platform_version") or "").strip()
    if min_platform_version:
        warnings.append(f"min_platform_version declared as {min_platform_version}; platform version enforcement is declarative")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "scope": scope,
        "compatibility": compatibility,
        "tenant_id": tenant_id,
    }


def validate_package(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Schema and integrity checks for a package payload.
    Returns a structured validation result.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "errors": ["Payload must be a dict"],
            "warnings": warnings,
        }

    package_id = str(payload.get("id") or "").strip()
    version = str(payload.get("version") or "").strip()
    scope = str(payload.get("scope") or "tenant").strip() or "tenant"
    compatibility = payload.get("compatibility") or {}
    payload_sections = payload.get("payload_sections") or {}
    raw_dependencies = payload.get("dependencies") or compatibility.get("dependencies") or []

    if not package_id:
        errors.append("Missing package id")
    if not version:
        errors.append("Missing package version")
    if not isinstance(compatibility, dict):
        errors.append("compatibility must be a dict")
        compatibility = {}
    if not isinstance(payload_sections, dict):
        errors.append("payload_sections must be a dict")
        payload_sections = {}
    try:
        dependencies = _normalize_dependencies(raw_dependencies)
    except ValueError as exc:
        errors.append(str(exc))
        dependencies = []

    if not payload_sections:
        warnings.append("Package has no payload sections")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "package_id": package_id,
        "version": version,
        "scope": scope,
        "dependencies": dependencies,
        "compatibility": compatibility,
        "payload_sections": payload_sections,
        "package_type": _infer_package_type(payload_sections),
        "impact_summary": _build_impact_summary(payload_sections),
        "metadata_usage_preview": _collect_metadata_usages(payload_sections, package_id),
    }


def preview_diff(
    tenant_id: Optional[Any],
    package_id: str,
    version: str,
    payload_sections: dict[str, Any],
    *,
    scope: str = "tenant",
    compatibility: Optional[dict[str, Any]] = None,
    dependencies: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Show changes to metadata vs current state for the tenant.
    Returns a structured summary with compatibility, impact, and dependency details.
    """
    payload = {
        "id": package_id,
        "version": version,
        "scope": scope,
        "compatibility": compatibility or {},
        "dependencies": dependencies or [],
        "payload_sections": payload_sections,
    }
    validation = validate_package(payload)
    compatibility_report = _compatibility_report(
        tenant_id,
        validation["scope"],
        validation["compatibility"],
        validation["dependencies"],
    )
    current = list(
        InstalledPackage.objects.filter(package_id=package_id, school_id=tenant_id, is_active=True).values_list("version", flat=True)
    )
    errors = list(validation["errors"]) + list(compatibility_report["errors"])
    warnings = list(validation["warnings"]) + list(compatibility_report["warnings"])
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "current_versions": current,
        "package_id": package_id,
        "version": version,
        "scope": validation["scope"],
        "dependencies": validation["dependencies"],
        "compatibility": compatibility_report,
        "package_type": validation["package_type"],
        "impacted_artifacts": validation["impact_summary"],
        "metadata_usage_preview": validation["metadata_usage_preview"],
        "proposed": {
            "package_id": package_id,
            "version": version,
            "sections": list((payload_sections or {}).keys()),
        },
    }


def apply_package(
    tenant_id: Optional[Any],
    package_id: str,
    version: str,
    payload_sections: dict[str, Any],
    mode: str = "production",
    actor_id: Optional[int] = None,
    *,
    scope: str = "tenant",
    compatibility: Optional[dict[str, Any]] = None,
    dependencies: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Write package to tenant with audit trail and impact metadata.
    mode: sandbox | test | production.
    """
    preview = preview_diff(
        tenant_id,
        package_id,
        version,
        payload_sections,
        scope=scope,
        compatibility=compatibility,
        dependencies=dependencies,
    )
    if not preview["ok"]:
        return {
            "ok": False,
            "errors": preview["errors"],
            "warnings": preview["warnings"],
            "package_id": package_id,
            "version": version,
        }

    rollback_token = uuid.uuid4().hex[:32]
    reconciliation_status = "reconciled" if mode == "production" else "applied"
    with transaction.atomic():
        PackageVersion.objects.update_or_create(
            package_id=package_id,
            version=version,
            defaults={
                "dependencies": preview["dependencies"],
                "compatibility": preview["compatibility"]["compatibility"],
                "payload_sections": payload_sections,
                "impact_summary": preview["impacted_artifacts"],
                "changelog_summary": ", ".join(preview["proposed"]["sections"]),
            },
        )
        inst = InstalledPackage.objects.create(
            package_id=package_id,
            package_type=preview["package_type"],
            version=version,
            school_id=tenant_id,
            scope=("sandbox" if mode == "sandbox" else scope) if tenant_id else "platform",
            applied_by_id=actor_id,
            rollback_token=rollback_token,
            dependency_snapshot=preview["dependencies"],
            impact_summary=preview["impacted_artifacts"],
            apply_stage=mode,
            reconciliation_status=reconciliation_status,
        )
        log = PackageChangeLog.objects.create(
            package_id=package_id,
            version=version,
            school_id=tenant_id,
            mode=mode,
            action="apply",
            rollback_token=rollback_token,
            actor_id=actor_id,
            dependency_snapshot=preview["dependencies"],
            impact_summary=preview["impacted_artifacts"],
            reconciliation_status=reconciliation_status,
        )
        _register_metadata_usages(preview["metadata_usage_preview"])
    return {
        "ok": True,
        "installed_id": inst.pk,
        "rollback_token": rollback_token,
        "changelog_id": log.pk,
        "stage": mode,
        "reconciliation_status": reconciliation_status,
        "dependencies": preview["dependencies"],
        "compatibility": preview["compatibility"],
        "impacted_artifacts": preview["impacted_artifacts"],
        "metadata_usage_preview": preview["metadata_usage_preview"],
        "warnings": preview["warnings"],
    }


def rollback(installed_package: InstalledPackage, actor_id: Optional[int] = None) -> dict[str, Any]:
    """
    Deactivate an installed package and record rollback in PackageChangeLog.
    """
    with transaction.atomic():
        installed_package.is_active = False
        installed_package.apply_stage = "rollback"
        installed_package.reconciliation_status = "rolled_back"
        installed_package.save(update_fields=["is_active", "apply_stage", "reconciliation_status"])
        log = PackageChangeLog.objects.create(
            package_id=installed_package.package_id,
            version=installed_package.version,
            school_id=installed_package.school_id,
            mode="production",
            action="rollback",
            rollback_token=installed_package.rollback_token or "",
            actor_id=actor_id,
            dependency_snapshot=installed_package.dependency_snapshot,
            impact_summary=installed_package.impact_summary,
            reconciliation_status="rolled_back",
        )
    return {
        "ok": True,
        "changelog_id": log.pk,
        "reconciliation_status": "rolled_back",
        "rollback_token": installed_package.rollback_token,
        "dependencies": installed_package.dependency_snapshot,
        "impacted_artifacts": installed_package.impact_summary,
    }


def promote_package(
    installed_package: InstalledPackage,
    *,
    actor_id: Optional[int] = None,
    target_mode: str = "production",
) -> dict[str, Any]:
    """
    Promote a sandbox or test install to a later stage without changing package identity.
    """
    previous_mode = installed_package.apply_stage
    next_scope = "tenant" if installed_package.scope == "sandbox" and target_mode == "production" else installed_package.scope
    reconciliation_status = "promoted" if target_mode != "production" else "reconciled"
    with transaction.atomic():
        installed_package.apply_stage = "promoted" if target_mode == "production" else target_mode
        installed_package.reconciliation_status = reconciliation_status
        installed_package.promoted_from_mode = previous_mode
        installed_package.scope = next_scope
        installed_package.save(
            update_fields=["apply_stage", "reconciliation_status", "promoted_from_mode", "scope"]
        )
        log = PackageChangeLog.objects.create(
            package_id=installed_package.package_id,
            version=installed_package.version,
            school_id=installed_package.school_id,
            mode=target_mode,
            action="promote",
            rollback_token=installed_package.rollback_token or "",
            actor_id=actor_id,
            dependency_snapshot=installed_package.dependency_snapshot,
            impact_summary=installed_package.impact_summary,
            reconciliation_status=reconciliation_status,
        )
    return {
        "ok": True,
        "installed_id": installed_package.pk,
        "changelog_id": log.pk,
        "from_stage": previous_mode,
        "to_stage": target_mode,
        "reconciliation_status": reconciliation_status,
        "impacted_artifacts": installed_package.impact_summary,
    }


class PackageEngine:
    """Facade for package operations (validate, preview, apply, rollback, promote)."""

    @staticmethod
    def validate_package(payload: dict[str, Any]) -> dict[str, Any]:
        return validate_package(payload)

    @staticmethod
    def preview_diff(
        tenant_id: Optional[Any],
        package_id: str,
        version: str,
        payload_sections: dict[str, Any],
        *,
        scope: str = "tenant",
        compatibility: Optional[dict[str, Any]] = None,
        dependencies: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        return preview_diff(
            tenant_id,
            package_id,
            version,
            payload_sections,
            scope=scope,
            compatibility=compatibility,
            dependencies=dependencies,
        )

    @staticmethod
    def apply_package(
        tenant_id: Optional[Any],
        package_id: str,
        version: str,
        payload_sections: dict[str, Any],
        mode: str = "production",
        actor_id: Optional[int] = None,
        *,
        scope: str = "tenant",
        compatibility: Optional[dict[str, Any]] = None,
        dependencies: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        return apply_package(
            tenant_id,
            package_id,
            version,
            payload_sections,
            mode=mode,
            actor_id=actor_id,
            scope=scope,
            compatibility=compatibility,
            dependencies=dependencies,
        )

    @staticmethod
    def rollback(installed_package: InstalledPackage, actor_id: Optional[int] = None) -> dict[str, Any]:
        return rollback(installed_package, actor_id=actor_id)

    @staticmethod
    def promote_package(
        installed_package: InstalledPackage,
        *,
        actor_id: Optional[int] = None,
        target_mode: str = "production",
    ) -> dict[str, Any]:
        return promote_package(installed_package, actor_id=actor_id, target_mode=target_mode)
