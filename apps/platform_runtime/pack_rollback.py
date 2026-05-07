"""Pack deactivation and rollback posture."""

from __future__ import annotations

from django.db import transaction

from apps.packages.engine import rollback as rollback_package
from apps.packages.models import InstalledPackage
from apps.platform_runtime.models import PackInstallation
from apps.platform_runtime.pack_audit import audit_pack_event


def deactivate_pack_installation(installation: PackInstallation, *, actor=None, confirmed: bool = False) -> dict:
    if not confirmed:
        return {"ok": False, "errors": ["Confirmation is required before deactivation."]}
    school = installation.school
    with transaction.atomic():
        installation.status = PackInstallation.Status.DEACTIVATED
        installation.save(update_fields=["status", "updated_at"])
        event = audit_pack_event(
            "pack_deactivated",
            pack_key=installation.pack_key,
            pack_type=installation.pack_type,
            school=school,
            actor=actor,
            result="deactivated",
            installation_id=installation.pk,
        )
    return {"ok": True, "status": installation.status, "audit_id": getattr(event, "pk", None)}


def rollback_pack_installation(installation: PackInstallation, *, actor=None, confirmed: bool = False) -> dict:
    school = installation.school
    audit_pack_event("pack_rollback_requested", pack_key=installation.pack_key, pack_type=installation.pack_type, school=school, actor=actor, result="requested", installation_id=installation.pk, payload={"confirmed": confirmed})
    if not confirmed:
        event = audit_pack_event("pack_rollback_failed", pack_key=installation.pack_key, pack_type=installation.pack_type, school=school, actor=actor, result="blocked", reason="confirmation_required", installation_id=installation.pk)
        return {"ok": False, "errors": ["Confirmation is required before rollback."], "audit_id": getattr(event, "pk", None)}
    if installation.status != PackInstallation.Status.APPLIED:
        event = audit_pack_event("pack_rollback_failed", pack_key=installation.pack_key, pack_type=installation.pack_type, school=school, actor=actor, result="blocked", reason="not_applied", installation_id=installation.pk)
        return {"ok": False, "errors": ["Only applied pack installations can be rolled back."], "audit_id": getattr(event, "pk", None)}
    with transaction.atomic():
        snapshot = installation.rollback_snapshot or {}
        if "settings" in snapshot:
            school.settings = snapshot.get("settings") or {}
            school.save(update_fields=["settings"])
        package_id = f"{installation.pack_type}:{installation.pack_key}"
        installed = InstalledPackage.objects.filter(package_id=package_id, version=installation.version, school=school, is_active=True).first()
        package_result = rollback_package(installed, actor_id=getattr(actor, "pk", None)) if installed else {"ok": True, "skipped": "no_active_package"}
        installation.status = PackInstallation.Status.ROLLED_BACK
        installation.save(update_fields=["status", "updated_at"])
        event = audit_pack_event(
            "pack_rolled_back",
            pack_key=installation.pack_key,
            pack_type=installation.pack_type,
            school=school,
            actor=actor,
            result="rolled_back",
            installation_id=installation.pk,
            payload={"reverted_changes": installation.applied_changes},
        )
    return {
        "ok": True,
        "reverted_changes": installation.applied_changes,
        "skipped_changes": [],
        "warnings": ["School data was not destructively deleted."],
        "requires_manual_review": bool((installation.rollback_snapshot or {}).get("manual_review")),
        "audit_id": getattr(event, "pk", None),
        "package_result": package_result,
    }
