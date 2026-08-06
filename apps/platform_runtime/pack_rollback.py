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
        # Surgically retract ONLY this pack's settings marker.
        #
        # apply_pack writes exactly one key —
        # settings["pack_installation_simulation"][pack.key]. A WHOLESALE
        # restore of the pre-apply snapshot (the previous behaviour) reverted
        # the ENTIRE settings dict, wiping every marker written after this pack
        # was applied: sibling packs, a later blueprint, tenant configuration.
        # A blueprint installs seven packs, so rolling one back could discard
        # six siblings' markers. This mirrors the surgical retraction already
        # applied to blueprint rollback for the same data-loss class.
        previous_settings = snapshot.get("settings")
        if isinstance(previous_settings, dict):
            settings = dict(school.settings or {})
            simulations = dict(settings.get("pack_installation_simulation") or {})
            previous_simulations = dict(
                previous_settings.get("pack_installation_simulation") or {}
            )
            changed = False
            if installation.pack_key in previous_simulations:
                # The pack was already recorded before this apply — restore that
                # entry rather than dropping it.
                if simulations.get(installation.pack_key) != previous_simulations[
                    installation.pack_key
                ]:
                    simulations[installation.pack_key] = previous_simulations[
                        installation.pack_key
                    ]
                    changed = True
            elif installation.pack_key in simulations:
                del simulations[installation.pack_key]
                changed = True
            if changed:
                settings["pack_installation_simulation"] = simulations
                school.settings = settings
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
