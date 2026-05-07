"""Rollback posture for blueprint marketplace installations."""

from __future__ import annotations

from django.db import transaction

from apps.packages.engine import rollback as rollback_package
from apps.packages.models import InstalledPackage
from apps.platform_runtime.blueprint_audit import audit_blueprint_event
from apps.platform_runtime.models import BlueprintInstallation


def rollback_blueprint_installation(
    installation: BlueprintInstallation,
    *,
    actor=None,
    confirmed: bool = False,
) -> dict[str, object]:
    if installation is None:
        return {"ok": False, "errors": ["Installation is required."]}
    audit_blueprint_event(
        "blueprint_rollback_requested",
        blueprint_key=installation.blueprint_key,
        school=installation.school,
        actor=actor,
        result="requested",
        installation_id=installation.pk,
        payload={"confirmed": confirmed},
    )
    if not confirmed:
        event = audit_blueprint_event(
            "blueprint_rollback_failed",
            blueprint_key=installation.blueprint_key,
            school=installation.school,
            actor=actor,
            result="blocked",
            reason="confirmation_required",
            installation_id=installation.pk,
        )
        return {
            "ok": False,
            "errors": ["Rollback confirmation is required."],
            "audit_id": getattr(event, "pk", None),
        }
    if installation.status != BlueprintInstallation.Status.APPLIED:
        event = audit_blueprint_event(
            "blueprint_rollback_failed",
            blueprint_key=installation.blueprint_key,
            school=installation.school,
            actor=actor,
            result="blocked",
            reason="installation_not_applied",
            installation_id=installation.pk,
        )
        return {
            "ok": False,
            "errors": ["Only applied blueprint installations can be rolled back."],
            "audit_id": getattr(event, "pk", None),
        }

    reverted_changes: list[str] = []
    skipped_changes: list[str] = []
    warnings = [
        "Rollback deactivates blueprint markers and restores settings snapshot; it does not delete school operational data."
    ]
    with transaction.atomic():
        school = installation.school
        snapshot = dict(installation.rollback_snapshot or {})
        if "settings" in snapshot:
            school.settings = dict(snapshot.get("settings") or {})
            school.save(update_fields=["settings"])
            reverted_changes.append("school.settings")
        else:
            skipped_changes.append("school.settings_snapshot_missing")
        installed_package = (
            InstalledPackage.objects.filter(
                school=school,
                package_id=f"blueprint:{installation.blueprint_key}",
                version=installation.blueprint_version,
                is_active=True,
            )
            .order_by("-applied_at")
            .first()
        )
        if installed_package:
            rollback_package(installed_package, actor_id=getattr(actor, "pk", None))
            reverted_changes.append("installed_package_marker")
        else:
            skipped_changes.append("installed_package_marker_missing")
        installation.status = BlueprintInstallation.Status.ROLLED_BACK
        installation.save(update_fields=["status", "updated_at"])
        event = audit_blueprint_event(
            "blueprint_rolled_back",
            blueprint_key=installation.blueprint_key,
            school=school,
            actor=actor,
            result="rolled_back",
            installation_id=installation.pk,
            payload={"reverted_changes": reverted_changes},
        )
    return {
        "ok": True,
        "reverted_changes": reverted_changes,
        "skipped_changes": skipped_changes,
        "warnings": warnings,
        "requires_manual_review": bool(installation.external_blockers),
        "audit_id": getattr(event, "pk", None),
    }
