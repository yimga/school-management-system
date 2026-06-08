#!/usr/bin/env python3
"""Exercise audit retention with only the required SQLite tables."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.db import connections
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import override_settings
from django.utils import timezone

from apps.compliance.audit_retention import (
    create_archive,
    purge_verified_archive,
    verify_archive,
)
from apps.compliance.models_audit import (
    AuditArchiveRecord,
    AuditLegalHold,
    AuditLog,
)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        database_path = Path(tmp) / "retention.sqlite3"
        alias = "audit_retention_verify"
        connections.databases[alias] = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(database_path),
            "OPTIONS": {},
            "TIME_ZONE": None,
            "CONN_HEALTH_CHECKS": False,
            "CONN_MAX_AGE": 0,
            "AUTOCOMMIT": True,
            "ATOMIC_REQUESTS": False,
            "USER": "",
            "PASSWORD": "",
            "HOST": "",
            "PORT": "",
            "TEST": {
                "CHARSET": None,
                "COLLATION": None,
                "MIGRATE": True,
                "MIRROR": None,
                "NAME": None,
            },
        }
        connection = connections[alias]
        try:
            with connection.schema_editor() as editor:
                editor.create_model(get_user_model())
                editor.create_model(AuditLog)
                editor.create_model(AuditLegalHold)
                editor.create_model(AuditArchiveRecord)

            cutoff = timezone.now() - timedelta(days=30)
            with override_settings(
                AUDIT_ARCHIVE_ROOT=str(Path(tmp) / "archives"),
                AUDIT_ARCHIVE_SIGNING_KEY="minimal-verification-signing-key",
                AUDIT_RETENTION_APPROVAL_TOKEN="minimal-verification-approval",
            ):
                held = AuditLog.objects.using(alias).create(
                    action=AuditLog.Action.VIEW,
                    model_name="Student",
                    object_id="held",
                    app_label="students",
                    sensitivity=AuditLog.Sensitivity.HIGH,
                )
                eligible = AuditLog.objects.using(alias).create(
                    action=AuditLog.Action.VIEW,
                    model_name="Student",
                    object_id="eligible",
                    app_label="students",
                    sensitivity=AuditLog.Sensitivity.HIGH,
                )
                range_held = AuditLog.objects.using(alias).create(
                    action=AuditLog.Action.VIEW,
                    model_name="Student",
                    object_id="range-held",
                    app_label="students",
                    sensitivity=AuditLog.Sensitivity.HIGH,
                )
                AuditLog.objects.using(alias).filter(
                    pk__in=[held.pk, eligible.pk, range_held.pk]
                ).update(timestamp=cutoff - timedelta(days=1))
                AuditLegalHold.objects.using(alias).create(
                    name="Verification hold",
                    reason="Prove held rows are excluded",
                    model_label=AuditLog._meta.label,
                    object_id=str(held.pk),
                )
                AuditLegalHold.objects.using(alias).create(
                    name="Verification date range",
                    reason="Prove date-range holds are applied to record timestamps",
                    model_label=AuditLog._meta.label,
                    starts_at=cutoff - timedelta(days=2),
                    ends_at=cutoff,
                )
                AuditLog.objects.using(alias).filter(pk=eligible.pk).update(
                    timestamp=cutoff - timedelta(days=10)
                )
                result = create_archive(
                    AuditLog, "timestamp", cutoff, using=alias
                )
                if result.eligible_count != 1 or result.held_count != 2:
                    raise RuntimeError("Legal-hold selection failed.")
                if verify_archive(result.archive) != [str(eligible.pk)]:
                    raise RuntimeError(
                        "Archive verification returned unexpected IDs."
                    )
                deleted = purge_verified_archive(
                    result.archive,
                    AuditLog,
                    approval_token="minimal-verification-approval",
                    using=alias,
                )
                if deleted != 1:
                    raise RuntimeError("Exact-row purge failed.")
                if AuditLog.objects.using(alias).filter(pk=eligible.pk).exists():
                    raise RuntimeError("Archived row survived purge.")
                if not AuditLog.objects.using(alias).filter(pk=held.pk).exists():
                    raise RuntimeError("Held row was purged.")
                if not AuditLog.objects.using(alias).filter(pk=range_held.pk).exists():
                    raise RuntimeError("Date-range held row was purged.")

                invalid_token_row = AuditLog.objects.using(alias).create(
                    action=AuditLog.Action.VIEW,
                    model_name="Student",
                    object_id="invalid-token",
                    app_label="students",
                    sensitivity=AuditLog.Sensitivity.HIGH,
                )
                AuditLog.objects.using(alias).filter(pk=invalid_token_row.pk).update(
                    timestamp=cutoff - timedelta(days=10)
                )
                invalid_token_archive = create_archive(
                    AuditLog, "timestamp", cutoff, using=alias
                ).archive
                try:
                    purge_verified_archive(
                        invalid_token_archive,
                        AuditLog,
                        approval_token="wrong",
                        using=alias,
                    )
                except PermissionDenied:
                    pass
                else:
                    raise RuntimeError("Invalid approval token did not fail closed.")

                tamper_row = AuditLog.objects.using(alias).create(
                    action=AuditLog.Action.VIEW,
                    model_name="Student",
                    object_id="tamper",
                    app_label="students",
                    sensitivity=AuditLog.Sensitivity.HIGH,
                )
                AuditLog.objects.using(alias).filter(pk=tamper_row.pk).update(
                    timestamp=cutoff - timedelta(days=10)
                )
                tamper_archive = create_archive(
                    AuditLog, "timestamp", cutoff, using=alias
                ).archive
                archive_path = Path(tmp) / "archives" / tamper_archive.relative_path
                archive_path.write_bytes(archive_path.read_bytes() + b"tampered")
                try:
                    verify_archive(tamper_archive)
                except PermissionDenied:
                    pass
                else:
                    raise RuntimeError("Tampered archive did not fail closed.")
        finally:
            connection.close()
    print(
        "AUDIT_RETENTION_MINIMAL_PASS "
        "archived=1 held=2 purged=1 invalid_token=blocked tamper=blocked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
