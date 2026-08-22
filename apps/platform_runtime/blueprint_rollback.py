"""Rollback posture for blueprint marketplace installations."""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.packages.engine import rollback as rollback_package
from apps.packages.models import InstalledPackage
from apps.platform_runtime.blueprint_audit import audit_blueprint_event
from apps.platform_runtime.models import BlueprintInstallation

logger = logging.getLogger(__name__)


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
    if installation.status not in {
        BlueprintInstallation.Status.APPLIED,
        BlueprintInstallation.Status.PARTIALLY_APPLIED,
    }:
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
            "errors": [
                "Only applied or partially applied blueprint installations can be rolled back."
            ],
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
        # Retract the packs this blueprint installed, FIRST.
        #
        # apply_blueprint installs the blueprint's dashboard/workflow/policy
        # packs as child PackInstallation rows. Rollback never touched them, so
        # a tenant who undid a blueprint was told "rolled_back" while all of its
        # packs stayed status=applied — for private-primary-school that is seven,
        # including the "Finance Approval" (dual approval, reconciliation
        # required) and "Parent Communication" (guardian visibility, consent)
        # POLICY bundles, which keep enforcing rules the tenant just retracted.
        #
        # Ordered before the settings retraction below because a pack's own
        # retraction touches settings["pack_installation_simulation"]; doing it
        # first keeps each layer undoing only what it wrote, newest first.
        from apps.platform_runtime.models import PackInstallation
        from apps.platform_runtime.pack_rollback import rollback_pack_installation

        child_packs = list(
            installation.pack_installations.filter(
                status=PackInstallation.Status.APPLIED
            ).order_by("-applied_at", "-id")
        )
        rolled_back_packs: list[str] = []
        for pack_installation in child_packs:
            try:
                pack_result = rollback_pack_installation(
                    pack_installation, actor=actor, confirmed=True
                )
            except Exception:  # noqa: BLE001 — one bad pack must not strand the rest
                logger.exception(
                    "blueprint rollback: child pack rollback raised school=%s pack=%s",
                    getattr(school, "pk", None),
                    pack_installation.pack_key,
                )
                skipped_changes.append(f"pack:{pack_installation.pack_key}")
                continue
            if pack_result.get("ok"):
                rolled_back_packs.append(pack_installation.pack_key)
            else:
                skipped_changes.append(f"pack:{pack_installation.pack_key}")
        if rolled_back_packs:
            reverted_changes.append("pack_installations")
        # Surgically retract ONLY this blueprint's settings markers.
        # apply_blueprint writes settings["blueprint_marketplace"][key] and
        # settings["local_first_blueprints"][key]. A WHOLESALE restore of the
        # pre-apply snapshot (the previous behaviour) reverted the entire
        # settings dict — wiping markers that a LATER, still-installed blueprint
        # had added, a cross-blueprint data-loss edge. This mirrors the surgical
        # features rollback below: touch only the keys THIS blueprint owns and
        # leave every other blueprint's markers and the tenant's own settings
        # intact. (snapshot["settings"] is retained for audit but not restored.)
        key = installation.blueprint_key
        settings = dict(school.settings or {})
        snapshot_settings = snapshot.get("settings")
        settings_changed = False
        # Remove this blueprint's per-blueprint keyed markers.
        for marker_bucket in ("blueprint_marketplace", "local_first_blueprints"):
            bucket = dict(settings.get(marker_bucket) or {})
            if key in bucket:
                del bucket[key]
                settings[marker_bucket] = bucket
                settings_changed = True
                if marker_bucket == "local_first_blueprints":
                    reverted_changes.append("offline_manifest_invalidation")
        # Decide how to reconcile the non-keyed global settings this apply also
        # wrote (e.g. pack_installation_simulation). When NO other blueprint
        # remains, restore the pre-apply snapshot wholesale so those global keys
        # are cleaned up too (single-blueprint rollback returns settings to their
        # exact pre-apply shape). When OTHER blueprints are still installed, keep
        # the rest of settings intact — a wholesale restore would wipe a later,
        # still-installed blueprint's markers (the cross-blueprint data-loss bug).
        remaining_blueprints = settings.get("blueprint_marketplace") or {}
        if not remaining_blueprints:
            if isinstance(snapshot_settings, dict):
                settings = dict(snapshot_settings)
                settings_changed = True
            else:
                for marker_bucket in ("blueprint_marketplace", "local_first_blueprints"):
                    if not settings.get(marker_bucket):
                        settings.pop(marker_bucket, None)
        if settings_changed:
            school.settings = settings
            school.save(update_fields=["settings"])
            reverted_changes.append("school.settings")
        else:
            skipped_changes.append("blueprint_settings_markers_missing")
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
        # Retire any sibling rows for the same blueprint_key. Version bumps use
        # different idempotency keys, so a tenant can hold multiple ``applied``
        # rows; rolling back one must not leave a stale row blocking the next base.
        superseded = list(
            BlueprintInstallation.objects.filter(
                school=school,
                blueprint_key=installation.blueprint_key,
                status__in=(
                    BlueprintInstallation.Status.APPLIED,
                    BlueprintInstallation.Status.PARTIALLY_APPLIED,
                ),
            )
            .exclude(pk=installation.pk)
            .values_list("pk", flat=True)
        )
        if superseded:
            BlueprintInstallation.objects.filter(pk__in=superseded).update(
                status=BlueprintInstallation.Status.ROLLED_BACK,
                updated_at=timezone.now(),
            )
            reverted_changes.append("superseded_sibling_installations")
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
    from apps.platform_runtime.installation_reconciliation import (
        finalize_installation_mutation,
    )

    finalize_installation_mutation(
        school,
        context=f"blueprint_rollback:{installation.blueprint_key}",
        actor=actor,
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
