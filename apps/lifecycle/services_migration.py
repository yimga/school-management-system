"""Wave L5 — migration auto-launch hook.

When a new school is created with `school.settings['migration_intent']`
populated, this service drafts a MigrationBundle so the school can land
on /portal/migration/status/ with an active bundle from day one — no
operator hunt for the wizard.

`migration_intent` is a small dict (set by the wizard, the bulk
creator, or the clone API) with shape:

    {
        "vendor": "powerschool" | "blackbaud" | "veracross" | "alma" |
                  "facts" | "skyward" | "oneroster" | "runmycampus" |
                  "csv",
        "intake_method": "file_upload" | ...  (matches IntakeMethod),
        "expected_students": <int> | null,
        "label": "Sept 2026 cutover" (optional)
    }

Returns the existing bundle if one already exists (idempotent).
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Optional

from .models import SchoolLifecycleStage
from .services import record_stage

logger = logging.getLogger(__name__)


_VALID_INTAKE_METHODS = {
    "file_upload",
    "archive",
    "url",
    "sftp",
    "s3",
    "sql_dump",
    "database",
    "oauth_folder",
    "email",
    "api_pull",
    "pdf",
    "access_db",
}


def ensure_draft_migration_bundle(school) -> Optional["object"]:
    """Create a draft MigrationBundle if `school.settings['migration_intent']` is set.

    Returns the bundle if one was created (or already existed), None
    otherwise. Safe to call from signals, mgmt commands, or post-create
    hooks. Never raises — best-effort.
    """
    if not school or not getattr(school, "id", None):
        return None
    settings_dict = getattr(school, "settings", None) or {}
    if not isinstance(settings_dict, dict):
        return None
    intent = settings_dict.get("migration_intent")
    if not isinstance(intent, dict) or not intent:
        return None
    try:
        from apps.migration_cloud.models import (
            BundleStatus,
            IntakeMethod,
            MigrationBundle,
        )

        # Idempotency: one draft bundle per school until applied.
        existing = MigrationBundle.objects.filter(
            school=school, status=BundleStatus.PENDING
        ).first()
        if existing is not None:
            return existing
        intake_method = (intent.get("intake_method") or "file_upload").lower()
        if intake_method not in _VALID_INTAKE_METHODS:
            intake_method = IntakeMethod.FILE_UPLOAD
        label = (intent.get("label") or "Initial migration")[:200]
        # idempotency_key derived from school + intent fingerprint so
        # rapid double-fires don't create duplicates. Salted with a
        # short random suffix so genuine re-creation after deletion
        # also doesn't collide.
        intent_repr = f"{school.id}|{intake_method}|{intent.get('vendor', '')}|{secrets.token_hex(4)}"
        idempotency_key = hashlib.sha256(intent_repr.encode("utf-8")).hexdigest()[:64]
        bundle = MigrationBundle.objects.create(
            school=school,
            label=label,
            intake_method=intake_method,
            source_hint=(intent.get("vendor") or "")[:200],
            idempotency_key=idempotency_key,
            status=BundleStatus.PENDING,
        )
        locale_ctx = intent.get("locale_context")
        if not isinstance(locale_ctx, dict) or not locale_ctx:
            loc = (getattr(school, "settings", None) or {}).get("localization") or {}
            if isinstance(loc, dict) and loc.get("country_code"):
                from apps.siteconfig.signup_localization_bootstrap import (
                    build_migration_locale_context,
                )

                cycles = loc.get("education_cycles") or []
                if not cycles and loc.get("school_type_code"):
                    cycles = [str(loc.get("school_type_code"))]
                locale_ctx = build_migration_locale_context(
                    str(loc.get("country_code") or ""),
                    language_code=str(loc.get("language_code") or ""),
                    calendar_code=str(loc.get("calendar_code") or ""),
                    education_cycles=[str(c) for c in cycles if c],
                )
        if isinstance(locale_ctx, dict) and locale_ctx:
            snap = dict(bundle.progress_snapshot or {})
            snap["signup_locale_context"] = locale_ctx
            bundle.progress_snapshot = snap
            bundle.save(update_fields=["progress_snapshot"])
        record_stage(
            school,
            SchoolLifecycleStage.Stage.MIGRATING,
            note=f"Migration intent auto-drafted (vendor={intent.get('vendor', '?')})",
            payload={
                "source": "lifecycle.services_migration.ensure_draft_migration_bundle",
                "vendor": intent.get("vendor", ""),
                "intake_method": intake_method,
                "bundle_id": str(bundle.id),
            },
        )
        return bundle
    except ImportError:
        # Migration Cloud unavailable in this env — silent no-op.
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "lifecycle.ensure_draft_migration_bundle.failed school_id=%s err=%s",
            school.id,
            type(exc).__name__,
        )
        return None


def tenant_status_snapshot(school) -> dict:
    """Public-safe per-tenant migration status for the portal status page.

    PII-safe: never returns artifact filenames, sample rows, or
    operator notes. Returns a small dict suitable for the
    /portal/migration/status/ template.
    """
    out: dict = {
        "school_slug": getattr(school, "slug", "") if school else "",
        "bundles": [],
        "active_bundle": None,
    }
    if not school or not getattr(school, "id", None):
        return out
    try:
        from apps.migration_cloud.models import MigrationBundle

        rows = (
            MigrationBundle.objects.filter(school=school)
            .order_by("-id")
            .only("id", "status", "intake_method", "source_hint", "label", "sla_tier")[:10]
        )
        for bundle in rows:
            out["bundles"].append(
                {
                    "id": str(bundle.id),
                    "label": bundle.label or "Untitled bundle",
                    "status": bundle.status,
                    "intake_method": bundle.intake_method,
                    "vendor_hint": bundle.source_hint,
                    "sla_tier": bundle.sla_tier,
                }
            )
        if out["bundles"]:
            out["active_bundle"] = out["bundles"][0]
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "lifecycle.tenant_status_snapshot.failed school_id=%s err=%s",
            school.id,
            type(exc).__name__,
        )
    return out
