"""Durable runtime activation for ExperienceTemplate packages.

The package engine owns preview/apply/rollback.  This module owns the missing
bridge between a successful generic package installation and the experience
state consumed by tenant shells and Setup Studio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.brand_experience.experience_templates import get_overlay
from apps.brand_experience.models_template import (
    TemplateAssignment,
    record_template_event,
)
from apps.packages.models import InstalledPackage
from apps.platform_runtime.models import PackInstallation
from apps.platform_runtime.pack_contract import get_pack


RUNTIME_SETTINGS_KEY = "active_experience_templates"


class ExperienceRuntimeError(ValueError):
    """Raised when an installation cannot be represented safely at runtime."""


@dataclass(frozen=True)
class ExperienceRuntimeResult:
    assignment_id: int
    installed_package_id: int
    template_key: str
    surface: str
    runtime: dict[str, Any]
    reconciled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "installed_package_id": self.installed_package_id,
            "template_key": self.template_key,
            "surface": self.surface,
            "runtime": self.runtime,
            "reconciled": self.reconciled,
        }


def build_experience_runtime_payload(
    template_key: str, *, platform_operator: bool = False
) -> dict[str, Any]:
    """Return a validated, JSON-safe runtime payload for ``template_key``."""

    pack = get_pack(template_key, pack_type="experience_template")
    overlay = get_overlay(template_key)
    if pack is None or overlay is None:
        raise ExperienceRuntimeError(
            f"Experience template {template_key!r} is not registered in both catalogs."
        )
    if overlay.is_operator_only() and not platform_operator:
        raise ExperienceRuntimeError(
            f"Operator-only template {template_key!r} cannot activate on a tenant."
        )
    now = timezone.now().isoformat()
    return {
        "template_key": template_key,
        "name": pack.name,
        "surface": overlay.category,
        "layout": pack.layout,
        "layout_family": overlay.layout_family,
        "layout_family_name": overlay.as_dict()["layout_family_name"],
        "palette_family": overlay.palette_family,
        "typography_stack": overlay.typography_stack,
        "density_mode": pack.density_mode,
        "mobile_behavior": pack.mobile_behavior,
        "role_target": list(pack.target_roles),
        "widgets": list(pack.widgets),
        "empty_states": list(pack.empty_states),
        "dashboard_actions": list(pack.dashboard_actions),
        "local_profile_key": overlay.local_profile_ref,
        "accessibility_level": overlay.accessibility_level,
        "applied_at": now,
    }


def _find_installed_package(
    *, school, template_key: str, version: str, installed_package_id: int | None = None
) -> InstalledPackage | None:
    queryset = InstalledPackage.objects.filter(school=school)
    if installed_package_id:
        return queryset.filter(pk=installed_package_id).first()
    package_id = f"experience_template:{template_key}"
    installed = queryset.filter(package_id=package_id, version=version).first()
    if installed is not None:
        return installed
    # Compatibility for the pre-activation implementation.  It persisted the
    # correct stable package_id but inferred ``package_type=blueprint``.
    return queryset.filter(package_id__endswith=f":{template_key}", version=version).first()


def activate_experience_template(
    *,
    school,
    template_key: str,
    actor=None,
    installed_package_id: int | None = None,
    reconciled: bool = False,
    emit_audit: bool = True,
    platform_operator: bool = False,
) -> ExperienceRuntimeResult:
    """Activate an applied package and make its behavior visible to tenant shells.

    Activation is idempotent.  A surface has one active template; applying a new
    template for the same surface deactivates the prior generic package marker.
    """

    runtime = build_experience_runtime_payload(
        template_key, platform_operator=platform_operator
    )
    pack = get_pack(template_key, pack_type="experience_template")
    assert pack is not None  # validated above
    installed = _find_installed_package(
        school=school,
        template_key=template_key,
        version=pack.version,
        installed_package_id=installed_package_id,
    )
    if installed is None:
        raise ExperienceRuntimeError(
            f"No active InstalledPackage exists for experience template {template_key!r}."
        )

    surface = str(runtime["surface"])
    with transaction.atomic():
        installed = InstalledPackage.objects.select_for_update().get(pk=installed.pk)
        if not installed.is_active or installed.package_type != "experience_pack":
            installed.is_active = True
            installed.package_type = "experience_pack"
            installed.reconciliation_status = "reconciled"
            installed.save(
                update_fields=["is_active", "package_type", "reconciliation_status"]
            )

        prior_assignments = list(
            TemplateAssignment.objects.select_related("installed_package")
            .select_for_update()
            .filter(
                installed_package__school=school,
                installed_package__is_active=True,
                surface=surface,
            )
            .exclude(installed_package=installed)
        )
        for prior in prior_assignments:
            prior.installed_package.is_active = False
            prior.installed_package.reconciliation_status = "rolled_back"
            prior.installed_package.save(
                update_fields=["is_active", "reconciliation_status"]
            )

        settings = dict(getattr(school, "settings", {}) or {})
        active = dict(settings.get(RUNTIME_SETTINGS_KEY) or {})
        previous_surface = active.get(surface)
        active[surface] = runtime
        settings[RUNTIME_SETTINGS_KEY] = active
        school.settings = settings
        school.save(update_fields=["settings"])

        assignment, _ = TemplateAssignment.objects.update_or_create(
            installed_package=installed,
            defaults={
                "template_key": template_key,
                "local_profile_key": str(runtime.get("local_profile_key") or ""),
                "surface": surface,
                "role_target": list(runtime.get("role_target") or []),
                "applied_by": actor if getattr(actor, "pk", None) else None,
                "rollback_snapshot": {
                    "runtime_surface": previous_surface,
                    "surface": surface,
                },
            },
        )

        if emit_audit:
            record_template_event(
                tenant_slug=getattr(school, "slug", "") or "",
                event_type="template.applied",
                template_key=template_key,
                local_profile_key=assignment.local_profile_key,
                actor_id=getattr(actor, "pk", None),
                payload={
                    "assignment_id": assignment.pk,
                    "installed_package_id": installed.pk,
                    "surface": surface,
                    "reconciled": reconciled,
                    "roles": assignment.role_target,
                },
            )

    return ExperienceRuntimeResult(
        assignment_id=assignment.pk,
        installed_package_id=installed.pk,
        template_key=template_key,
        surface=surface,
        runtime=runtime,
        reconciled=reconciled,
    )


def reconcile_latest_experience_template(*, school, actor=None) -> ExperienceRuntimeResult | None:
    """Self-heal an applied pre-bridge installation without requiring re-apply."""

    latest = (
        PackInstallation.objects.filter(
            school=school,
            pack_type="experience_template",
            status=PackInstallation.Status.APPLIED,
        )
        .order_by("-applied_at", "-created_at")
        .first()
    )
    if latest is None:
        return None
    active_assignment = (
        TemplateAssignment.objects.filter(
            installed_package__school=school,
            installed_package__is_active=True,
            template_key=latest.pack_key,
        )
        .select_related("installed_package")
        .first()
    )
    active_runtime = dict(getattr(school, "settings", {}) or {}).get(
        RUNTIME_SETTINGS_KEY, {}
    )
    if active_assignment is not None and active_runtime.get(active_assignment.surface):
        payload = active_runtime[active_assignment.surface]
        return ExperienceRuntimeResult(
            assignment_id=active_assignment.pk,
            installed_package_id=active_assignment.installed_package_id,
            template_key=active_assignment.template_key,
            surface=active_assignment.surface,
            runtime=payload,
            reconciled=False,
        )
    installed = _find_installed_package(
        school=school,
        template_key=latest.pack_key,
        version=latest.version,
    )
    if installed is None:
        return None
    return activate_experience_template(
        school=school,
        template_key=latest.pack_key,
        actor=actor,
        installed_package_id=installed.pk,
        reconciled=True,
        emit_audit=True,
    )


def resolve_active_experience_template(*, school, role: str = "") -> dict[str, Any]:
    """Resolve the newest active runtime applicable to ``role``."""

    active = dict(getattr(school, "settings", {}) or {}).get(
        RUNTIME_SETTINGS_KEY, {}
    )
    if not isinstance(active, dict):
        return {}
    normalized_role = (role or "").strip().casefold()
    candidates: list[dict[str, Any]] = []
    for value in active.values():
        if not isinstance(value, dict):
            continue
        targets = {str(item).strip().casefold() for item in value.get("role_target") or []}
        if not normalized_role or not targets or normalized_role in targets:
            candidates.append(value)
        elif normalized_role in {"admin", "superadmin", "school_admin"} and "admin" in targets:
            candidates.append(value)
    if not candidates:
        return {}
    candidates.sort(key=lambda row: str(row.get("applied_at") or ""), reverse=True)
    return candidates[0]


def clear_experience_template_runtime(*, assignment: TemplateAssignment) -> None:
    """Restore the prior runtime slot after the package engine rolls back."""

    school = assignment.installed_package.school
    surface = assignment.surface
    with transaction.atomic():
        settings = dict(getattr(school, "settings", {}) or {})
        active = dict(settings.get(RUNTIME_SETTINGS_KEY) or {})
        previous = dict(assignment.rollback_snapshot or {}).get("runtime_surface")
        previous_assignment = None
        if isinstance(previous, dict) and previous.get("template_key"):
            previous_assignment = (
                TemplateAssignment.objects.select_related("installed_package")
                .select_for_update()
                .filter(
                    installed_package__school=school,
                    template_key=previous["template_key"],
                    surface=surface,
                )
                .exclude(pk=assignment.pk)
                .order_by("-applied_at")
                .first()
            )
        if previous_assignment is not None:
            previous_assignment.installed_package.is_active = True
            previous_assignment.installed_package.reconciliation_status = "reconciled"
            previous_assignment.installed_package.save(
                update_fields=["is_active", "reconciliation_status"]
            )
            active[surface] = previous
        else:
            active.pop(surface, None)
        settings[RUNTIME_SETTINGS_KEY] = active
        school.settings = settings
        school.save(update_fields=["settings"])
