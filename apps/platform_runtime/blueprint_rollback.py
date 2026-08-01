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
        "Rollback deactivates blueprint markers, restores settings snapshot, and invalidates the offline manifest; it does not delete school operational data."
    ]
    offline_manifest_invalidation = (
        (installation.preview_snapshot or {})
        .get("rollback_plan", {})
        .get("offline_manifest_invalidation", {})
    )
    with transaction.atomic():
        school = installation.school
        snapshot = dict(installation.rollback_snapshot or {})
        if "settings" in snapshot:
            school.settings = dict(snapshot.get("settings") or {})
            school.save(update_fields=["settings"])
            reverted_changes.append("school.settings")
            reverted_changes.append("offline_manifest_invalidation")
        else:
            skipped_changes.append("school.settings_snapshot_missing")
            settings = dict(school.settings or {})
            local_first = dict(settings.get("local_first_blueprints") or {})
            if installation.blueprint_key in local_first:
                local_first[installation.blueprint_key]["status"] = "rolled_back"
                local_first[installation.blueprint_key][
                    "offline_manifest_invalidation"
                ] = offline_manifest_invalidation
                settings["local_first_blueprints"] = local_first
                school.settings = settings
                school.save(update_fields=["settings"])
                reverted_changes.append("offline_manifest_invalidation")
        # Reverse the module bridge. apply_blueprint switches the blueprint's
        # implied feature codes on in School.features and records exactly which
        # ones it changed; undo precisely those. A wholesale restore of the
        # features snapshot would also wipe features the tenant turned on after
        # the apply, which rollback must never do.
        enabled_by_apply = list(snapshot.get("modules_enabled") or [])
        if enabled_by_apply:
            previous_features = dict(snapshot.get("features") or {})
            features = dict(getattr(school, "features", None) or {})
            features_changed = False
            for code in enabled_by_apply:
                if code in previous_features:
                    if features.get(code) != previous_features[code]:
                        features[code] = previous_features[code]
                        features_changed = True
                elif code in features:
                    del features[code]
                    features_changed = True
            if features_changed:
                school.features = features
                school.save(update_fields=["features", "updated_at"])
                reverted_changes.append("school.features")
                # Mirror the retraction into the toggle store, which is where an
                # "off" decision actually lives. Without this the store kept
                # advertising an enable this blueprint no longer stands behind.
                from apps.platform_runtime.blueprint_modules import (
                    _sync_module_toggle_state,
                )

                _sync_module_toggle_state(
                    school,
                    [code for code in enabled_by_apply if not features.get(code)],
                    enabled=False,
                )
                try:
                    from apps.policies.policy_registry import invalidate_policy_cache

                    invalidate_policy_cache(school)
                except Exception:  # noqa: BLE001 — cache invalidation is best-effort
                    pass
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
            payload={
                "reverted_changes": reverted_changes,
                "offline_manifest_invalidation": offline_manifest_invalidation,
            },
        )
    return {
        "ok": True,
        "reverted_changes": reverted_changes,
        "skipped_changes": skipped_changes,
        "warnings": warnings,
        "requires_manual_review": bool(installation.external_blockers),
        "audit_id": getattr(event, "pk", None),
        "offline_manifest_invalidation": offline_manifest_invalidation,
    }
