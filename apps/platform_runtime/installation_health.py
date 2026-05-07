"""Installation health summaries for configuration surfaces."""

from __future__ import annotations

from apps.platform_runtime.models import BlueprintInstallation, ConfigurationChangeRequest, PackInstallation


def _pending_request_exists(school, target_key: str, target_type: str) -> bool:
    return ConfigurationChangeRequest.objects.filter(
        school=school,
        target_key=target_key,
        target_type=target_type,
        status__in=[
            ConfigurationChangeRequest.Status.PENDING_APPROVAL,
            ConfigurationChangeRequest.Status.APPROVED,
        ],
    ).exists()


def _scheduled_request_exists(school, target_key: str, target_type: str) -> bool:
    return ConfigurationChangeRequest.objects.filter(
        school=school,
        target_key=target_key,
        target_type=target_type,
        status=ConfigurationChangeRequest.Status.SCHEDULED,
    ).exists()


def calculate_blueprint_installation_health(installation: BlueprintInstallation) -> dict:
    if _scheduled_request_exists(installation.school, installation.blueprint_key, "blueprint"):
        state = "scheduled"
    elif _pending_request_exists(installation.school, installation.blueprint_key, "blueprint"):
        state = "pending_approval"
    elif installation.status == BlueprintInstallation.Status.PARTIALLY_APPLIED:
        state = "partially_applied"
    elif installation.status in {BlueprintInstallation.Status.FAILED, BlueprintInstallation.Status.ROLLBACK_FAILED}:
        state = "failed"
    elif installation.external_blockers:
        state = "external_blocked"
    elif installation.status == BlueprintInstallation.Status.APPLIED and installation.rollback_snapshot:
        state = "rollback_available"
    elif installation.status == BlueprintInstallation.Status.ROLLED_BACK:
        state = "healthy"
    else:
        state = "healthy"
    return {
        "state": state,
        "rollback_available": bool(installation.rollback_snapshot),
        "external_blockers": installation.external_blockers,
        "upgrade_available": installation.upgrade_available,
    }


def calculate_pack_installation_health(installation: PackInstallation) -> dict:
    if _scheduled_request_exists(installation.school, installation.pack_key, installation.pack_type):
        state = "scheduled"
    elif _pending_request_exists(installation.school, installation.pack_key, installation.pack_type):
        state = "pending_approval"
    elif installation.status == PackInstallation.Status.PARTIALLY_APPLIED:
        state = "partially_applied"
    elif installation.status in {PackInstallation.Status.FAILED, PackInstallation.Status.ROLLBACK_FAILED}:
        state = "failed"
    elif installation.external_blockers:
        state = "external_blocked"
    elif installation.status == PackInstallation.Status.APPLIED and installation.rollback_snapshot:
        state = "rollback_available"
    elif installation.status in {PackInstallation.Status.DEACTIVATED, PackInstallation.Status.ROLLED_BACK}:
        state = "healthy"
    else:
        state = "healthy"
    return {
        "state": state,
        "rollback_available": bool(installation.rollback_snapshot),
        "external_blockers": installation.external_blockers,
        "upgrade_available": installation.upgrade_available,
    }
