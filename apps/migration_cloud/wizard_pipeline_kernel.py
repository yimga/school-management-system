"""Legacy data extraction wizard → Migration Cloud bundle + mapping ledger."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mc_bucket(school: Any | None) -> dict[str, Any]:
    if school is None:
        return {}
    settings = getattr(school, "settings", None) or {}
    return dict((settings.get("migration_cloud") or {}))


def _save_mc(school: Any | None, mc: dict[str, Any]) -> None:
    if school is None:
        return
    mc["updated_at"] = _utc_now()
    settings = dict(getattr(school, "settings", None) or {})
    settings["migration_cloud"] = mc
    school.settings = settings
    school.save(update_fields=["settings"])


def _latest_bundle(school: Any):
    from apps.migration_cloud.models import MigrationBundle

    return (
        MigrationBundle.objects.filter(school=school)
        .order_by("-created_at")
        .first()
    )


def apply_field_mapping(
    *,
    school: Any | None,
    payload: dict[str, Any],
    actor_user_id: int | None = None,
) -> dict[str, Any]:
    mapping = payload.get("mapping") or payload.get("value") or payload
    if not isinstance(mapping, dict):
        mapping = {"raw": mapping}

    mc = _mc_bucket(school)
    mc["field_vector_mapping"] = mapping
    _save_mc(school, mc)

    if school is not None:
        bundle = _latest_bundle(school)
        if bundle is not None:
            summary = dict(bundle.size_summary or {})
            summary["field_vector_mapping"] = mapping
            summary["mapping_updated_at"] = _utc_now()
            if actor_user_id:
                summary["mapping_actor_user_id"] = actor_user_id
            bundle.size_summary = summary
            bundle.save(update_fields=["size_summary", "updated_at"])

    return {"ok": True, "field_vector_mapping": mapping}


def apply_error_cleanup(
    *,
    school: Any | None,
    payload: dict[str, Any],
    actor_user_id: int | None = None,
) -> dict[str, Any]:
    cleanup = {
        k: payload.get(k)
        for k in ("confirm_known_errors", "strip_blank_rows", "dedupe_by_email")
        if k in payload
    }
    mc = _mc_bucket(school)
    mc["inline_error_cleanup"] = cleanup
    _save_mc(school, mc)

    if school is not None:
        bundle = _latest_bundle(school)
        if bundle is not None:
            summary = dict(bundle.size_summary or {})
            logs = list(summary.get("worker_log") or [])
            logs.append(
                {
                    "ts": _utc_now(),
                    "event": "wizard.cleanup_ack",
                    "cleanup": cleanup,
                    "actor_user_id": actor_user_id,
                }
            )
            summary["worker_log"] = logs[-50:]
            summary["inline_error_cleanup"] = cleanup
            bundle.size_summary = summary
            bundle.save(update_fields=["size_summary", "updated_at"])

    return {"ok": True, "inline_error_cleanup": cleanup}


def apply_seeding_mode(
    *,
    school: Any | None,
    payload: dict[str, Any],
    actor_user_id: int | None = None,
) -> dict[str, Any]:
    mode = payload.get("value") or payload.get("seeding_mode") or "dry_run"
    mc = _mc_bucket(school)
    mc["identity_seeding_mode"] = mode
    _save_mc(school, mc)

    bundle_id = None
    if school is not None and mode in ("commit_to_staging", "commit_to_production"):
        try:
            from apps.migration_cloud.services.intake_init import bootstrap_migration_bundle

            bundle_id = bootstrap_migration_bundle(
                school=school,
                source=mc.get("wizard_source") or "csv_canonical",
                actor_id=actor_user_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("apply_seeding_mode bootstrap failed: %s", exc)

        bundle = _latest_bundle(school)
        if bundle is not None:
            summary = dict(bundle.size_summary or {})
            summary["seeding_mode"] = mode
            summary["seeding_ack_at"] = _utc_now()
            if actor_user_id:
                summary["seeding_actor_user_id"] = actor_user_id
            bundle.size_summary = summary
            bundle.save(update_fields=["size_summary", "updated_at"])

    return {"ok": True, "identity_seeding_mode": mode, "bundle_id": bundle_id}
