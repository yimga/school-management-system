"""
Export a regulator-ready compliance evidence bundle (SEC-607).

The bundle includes:
- DSAR/GDPR execution evidence
- Retention policy windows + current backlog counts
- Tenant policy lock snapshots
- Region feature compliance matrix
- Compliance scorecards from the compliance auditor
"""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.policies.policy_registry import get_effective_policy


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _infer_gdpr_action(*, details: dict[str, Any], description: str) -> str:
    action = str(details.get("gdpr_action") or "").strip()
    if action:
        return action

    text = (description or "").upper()
    if "ART. 20" in text or "PORTABILITY" in text:
        return "art20_portability"
    if "ART. 17" in text or "ERASURE" in text:
        return "art17_erasure"
    return ""


class Command(BaseCommand):
    help = "Export compliance evidence bundle for audit/go-live reviews."

    def add_arguments(self, parser):
        parser.add_argument(
            "--region",
            type=str,
            default="",
            help="Optional region filter (e.g. USA, CMR).",
        )
        parser.add_argument(
            "--school-slug",
            type=str,
            default="",
            help="Optional school slug filter.",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default="logs/compliance_evidence",
            help="Directory where the zip evidence pack will be written.",
        )
        parser.add_argument(
            "--output-file",
            type=str,
            default="",
            help="Optional explicit output .zip path (overrides --output-dir).",
        )
        parser.add_argument(
            "--include-inactive-schools",
            action="store_true",
            help="Include inactive schools in policy-lock snapshots.",
        )

    def _retention_windows(self) -> dict[str, int]:
        configured = dict(getattr(settings, "DATA_RETENTION", {}) or {})
        return {
            "audit_log_days": int(
                os.getenv("AUDIT_LOG_RETENTION_DAYS", configured.get("audit_log_days", 90))
            ),
            "access_log_days": int(
                os.getenv("ACCESS_LOG_RETENTION_DAYS", configured.get("access_log_days", 30))
            ),
            "session_days": int(
                os.getenv("ACTIVITY_SESSION_RETENTION_DAYS", configured.get("session_days", 60))
            ),
            "report_days": int(configured.get("report_days", 365)),
        }

    def _load_scorecards(self, *, region_filter: str) -> dict[str, Any]:
        out = io.StringIO()
        args = ["--json"]
        if region_filter:
            args.extend(["--region", region_filter])
        call_command("compliance_auditor", *args, stdout=out)
        payload = json.loads(out.getvalue() or "{}")
        if not isinstance(payload, dict):
            raise CommandError("compliance_auditor returned unexpected payload.")
        return payload

    def handle(self, *args, **options):
        from apps.compliance.models import ComplianceAuditLog, RegionFeatureCompliance
        from apps.compliance.models_audit import (
            AccessLog,
            AuditLog,
            ComplianceReport,
            UserActivitySession,
        )
        from apps.schools.models import School

        now = timezone.now()
        region_filter = str(options.get("region") or "").strip().upper()
        school_slug = str(options.get("school_slug") or "").strip()

        schools_qs = School.objects.select_related("default_region")
        if not options.get("include_inactive_schools"):
            schools_qs = schools_qs.filter(is_active=True)
        if region_filter:
            schools_qs = schools_qs.filter(default_region_id=region_filter)
        if school_slug:
            schools_qs = schools_qs.filter(slug=school_slug)

        schools = list(schools_qs.order_by("slug"))
        if school_slug and not schools:
            raise CommandError(f"School '{school_slug}' not found for requested filters.")

        selected_school_ids = {str(s.pk) for s in schools}
        selected_regions = sorted(
            {str(s.default_region_id) for s in schools if getattr(s, "default_region_id", None)}
        )

        dsar_events: list[dict[str, Any]] = []
        logs_qs = ComplianceAuditLog.objects.select_related("region").order_by("-timestamp")
        if region_filter:
            logs_qs = logs_qs.filter(region_id=region_filter)
        elif selected_regions:
            logs_qs = logs_qs.filter(region_id__in=selected_regions)

        for row in logs_qs.iterator():
            details = dict(row.details or {}) if isinstance(row.details, dict) else {}
            school_id = str(details.get("school_id") or "")
            if selected_school_ids and school_id and school_id not in selected_school_ids:
                continue
            if school_slug and not school_id:
                continue

            action = _infer_gdpr_action(details=details, description=str(row.description or ""))
            description = str(row.description or "")
            if not action and "GDPR" not in description.upper():
                continue

            dsar_events.append(
                {
                    "id": row.pk,
                    "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                    "region_code": str(row.region_id or ""),
                    "action_type": row.action_type,
                    "severity": row.severity,
                    "gdpr_action": action,
                    "school_id": school_id or None,
                    "student_id": details.get("student_id"),
                    "description": description,
                }
            )

        retention_windows = self._retention_windows()
        model_specs = [
            ("audit_logs", AuditLog, "timestamp", retention_windows["audit_log_days"]),
            ("access_logs", AccessLog, "timestamp", retention_windows["access_log_days"]),
            ("sessions", UserActivitySession, "login_timestamp", retention_windows["session_days"]),
            ("compliance_reports", ComplianceReport, "generated_at", retention_windows["report_days"]),
        ]
        retention_snapshot: dict[str, Any] = {
            "captured_at": now.isoformat(),
            "windows_days": retention_windows,
            "datasets": {},
        }
        for key, model, timestamp_field, days in model_specs:
            total_count = model.objects.count()
            overdue_count = 0
            cutoff = None
            if days > 0:
                cutoff = now - timedelta(days=days)
                overdue_count = model.objects.filter(**{f"{timestamp_field}__lt": cutoff}).count()
            retention_snapshot["datasets"][key] = {
                "model": model.__name__,
                "timestamp_field": timestamp_field,
                "retention_days": days,
                "cutoff": cutoff.isoformat() if cutoff else None,
                "total_records": total_count,
                "records_past_retention": overdue_count,
            }

        policy_locks: list[dict[str, Any]] = []
        for school in schools:
            school_settings = {**get_effective_policy(school), **dict(getattr(school, "settings", None) or {})}
            metadata = school_settings.get("tenant_config_metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {}

            locked_keys: list[str] = []
            approval_keys: list[str] = []
            non_editable_keys: list[str] = []
            for key, info in metadata.items():
                if not isinstance(info, dict):
                    continue
                if bool(info.get("compliance_locked")):
                    locked_keys.append(str(key))
                if bool(info.get("requires_approval")):
                    approval_keys.append(str(key))
                if not bool(info.get("tenant_editable", True)):
                    non_editable_keys.append(str(key))

            policy_locks.append(
                {
                    "school_id": str(school.pk),
                    "school_slug": school.slug,
                    "school_name": school.name,
                    "region_code": str(getattr(school, "default_region_id", "") or ""),
                    "tenant_policy_pack": school_settings.get("tenant_policy_pack") or {},
                    "metadata_keys_count": len(metadata),
                    "compliance_locked_keys": sorted(set(locked_keys)),
                    "requires_approval_keys": sorted(set(approval_keys)),
                    "tenant_non_editable_keys": sorted(set(non_editable_keys)),
                }
            )

        rules_qs = RegionFeatureCompliance.objects.select_related("region").order_by("region_id", "feature_code")
        if region_filter:
            rules_qs = rules_qs.filter(region_id=region_filter)
        elif selected_regions:
            rules_qs = rules_qs.filter(region_id__in=selected_regions)
        region_rule_rows = [
            {
                "region_code": str(rule.region_id),
                "feature_code": rule.feature_code,
                "status": rule.status,
                "notes": rule.notes,
                "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
            }
            for rule in rules_qs
        ]

        scorecards = self._load_scorecards(region_filter=region_filter)
        if school_slug:
            filtered_school_cards = [
                row
                for row in (scorecards.get("schools") or [])
                if str(row.get("school_slug") or "") == school_slug
            ]
            scorecards = dict(scorecards)
            scorecards["schools"] = filtered_school_cards

        output_file = str(options.get("output_file") or "").strip()
        if output_file:
            zip_path = Path(output_file).expanduser().resolve()
            if zip_path.suffix.lower() != ".zip":
                raise CommandError("--output-file must end with .zip")
            zip_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            output_dir = Path(str(options.get("output_dir") or "logs/compliance_evidence")).expanduser().resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            zip_path = output_dir / f"compliance_evidence_pack_{timestamp}.zip"

        manifest = {
            "generated_at": now.isoformat(),
            "region_filter": region_filter or None,
            "school_slug_filter": school_slug or None,
            "included_region_codes": selected_regions,
            "counts": {
                "schools": len(policy_locks),
                "dsar_events": len(dsar_events),
                "region_feature_rules": len(region_rule_rows),
                "locked_keys_total": sum(len(item["compliance_locked_keys"]) for item in policy_locks),
            },
            "files": [
                "manifest.json",
                "README.txt",
                "compliance_scorecard.json",
                "dsar_events.json",
                "policy_locks.json",
                "retention_snapshot.json",
                "region_feature_rules.csv",
            ],
        }

        with tempfile.TemporaryDirectory(prefix="compliance-evidence-") as temp_dir:
            temp_root = Path(temp_dir)
            _write_json(temp_root / "manifest.json", manifest)
            _write_json(temp_root / "compliance_scorecard.json", scorecards)
            _write_json(temp_root / "dsar_events.json", dsar_events)
            _write_json(temp_root / "policy_locks.json", policy_locks)
            _write_json(temp_root / "retention_snapshot.json", retention_snapshot)

            with (temp_root / "region_feature_rules.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["region_code", "feature_code", "status", "notes", "updated_at"],
                )
                writer.writeheader()
                for row in region_rule_rows:
                    writer.writerow(row)

            (temp_root / "README.txt").write_text(
                "\n".join(
                    [
                        "Compliance Evidence Pack",
                        "Generated for SEC-607 evidence export requirements.",
                        "",
                        "Contents:",
                        "- manifest.json: pack summary and counts",
                        "- compliance_scorecard.json: compliance auditor scorecards",
                        "- dsar_events.json: GDPR Art.17/Art.20 execution evidence",
                        "- policy_locks.json: tenant config lock metadata by school",
                        "- retention_snapshot.json: retention windows and backlog counts",
                        "- region_feature_rules.csv: region feature compliance matrix",
                    ]
                ),
                encoding="utf-8",
            )

            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for file_name in manifest["files"]:
                    archive.write(temp_root / file_name, arcname=file_name)

        self.stdout.write(self.style.SUCCESS(f"Compliance evidence pack written: {zip_path}"))
        self.stdout.write(
            json.dumps(
                {
                    "path": str(zip_path),
                    "schools": len(policy_locks),
                    "dsar_events": len(dsar_events),
                    "region_feature_rules": len(region_rule_rows),
                },
                sort_keys=True,
            )
        )
