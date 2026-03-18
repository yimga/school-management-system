"""
Periodic compliance health checks with region/school scorecards.

Run via Celery Beat or cron. Cross-tenant read-only checks:
- pending waiver requests
- RegionFeatureCompliance rule coverage for guard-controlled features
- school region assignment and policy snapshot presence

Usage:
  python manage.py compliance_auditor
  python manage.py compliance_auditor --json
  python manage.py compliance_auditor --region USA --strict --min-score 90
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import models

from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.policies.policy_registry import get_effective_policy

# §2.4: Typed allowlist for _resolve_guard_feature_codes import/attr fallback.
_COMPLIANCE_AUDITOR_RESOLVE_GUARD_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
)


@dataclass(frozen=True)
class SchoolComplianceResult:
    school_id: str
    school_slug: str
    region_code: str
    score: float
    checks: list[dict]


class Command(BaseCommand):
    help = (
        "Run compliance health checks (waivers, region rules, school policy snapshots) "
        "and output scorecards."
    )

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Output JSON")
        parser.add_argument(
            "--region",
            type=str,
            default="",
            help="Optional region code filter (e.g. USA, CMR).",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with non-zero status when score is below --min-score.",
        )
        parser.add_argument(
            "--min-score",
            type=float,
            default=80.0,
            help="Minimum compliance score required in --strict mode.",
        )

    def _score_from_checks(self, checks: list[dict]) -> float:
        if not checks:
            return 100.0
        ok_count = sum(1 for item in checks if bool(item.get("ok")))
        return round((ok_count / len(checks)) * 100.0, 2)

    def _resolve_guard_feature_codes(self) -> list[str]:
        try:
            from apps.compliance.middleware import COMPLIANCE_GUARD_PATH_MAP

            return sorted(
                {
                    str(v).strip()
                    for v in COMPLIANCE_GUARD_PATH_MAP.values()
                    if str(v).strip()
                }
            )
        except _COMPLIANCE_AUDITOR_RESOLVE_GUARD_ERRORS as e:
            log_exception_with_context(
                "compliance_auditor: resolve guard feature codes failed",
                school_id=None,
                extra={"command": "compliance_auditor", "error": str(e)},
            )
            # Conservative fallback for DSAR/interoperability paths.
            return sorted(
                {
                    "Export_All_Student_Data",
                    "Right_to_Erasure",
                    "Lead_Capture_API",
                    "OneRoster_Interop",
                    "LTI13_Interop",
                    "SCIM_Provisioning",
                }
            )

    def _build_school_scorecard(
        self,
        *,
        school,
        pending_waiver_count: int,
        core_features: list[str],
        rule_lookup: dict[str, dict[str, str]],
    ) -> SchoolComplianceResult:
        policy = get_effective_policy(school)
        settings = {**policy, **dict(getattr(school, "settings", None) or {})}
        region_code = str(getattr(school, "default_region_id", "") or "")
        region_rules = rule_lookup.get(region_code, {})

        missing_core = [code for code in core_features if code not in region_rules]
        dsar_codes = {"Right_to_Erasure", "Export_All_Student_Data"}
        disabled_dsar = [
            code for code in dsar_codes if region_rules.get(code) == "DISABLED"
        ]

        checks: list[dict] = [
            {
                "check": "school_has_default_region",
                "ok": bool(region_code),
                "value": region_code or None,
            },
            {
                "check": "tenant_policy_pack_present",
                "ok": bool((settings.get("tenant_policy_pack") or {}).get("code")),
                "value": (settings.get("tenant_policy_pack") or {}).get("code"),
            },
            {
                "check": "tenant_compiled_config_present",
                "ok": bool(
                    settings.get("tenant_compiled_config")
                    and settings.get("tenant_config_metadata")
                ),
                "value": bool(settings.get("tenant_compiled_config")),
            },
            {
                "check": "region_core_feature_rule_coverage",
                "ok": not missing_core,
                "value": {
                    "missing_count": len(missing_core),
                    "missing_features": missing_core,
                },
            },
            {
                "check": "dsar_rules_not_disabled",
                "ok": not disabled_dsar,
                "value": {"disabled_features": disabled_dsar},
            },
            {
                "check": "school_pending_waiver_requests_threshold",
                "ok": pending_waiver_count < 5,
                "value": pending_waiver_count,
            },
        ]

        return SchoolComplianceResult(
            school_id=str(school.pk),
            school_slug=str(getattr(school, "slug", "") or ""),
            region_code=region_code,
            score=self._score_from_checks(checks),
            checks=checks,
        )

    def handle(self, *args, **options):
        region_filter = str(options.get("region") or "").strip().upper()
        strict = bool(options.get("strict"))
        min_score = float(options.get("min_score") or 80.0)
        as_json = bool(options.get("json"))

        from apps.compliance.models import RegionFeatureCompliance
        from apps.schools.models import School
        from apps.siteconfig.models import WaiverRequest

        schools_qs = School.objects.select_related("default_region").filter(
            is_active=True
        )
        if region_filter:
            schools_qs = schools_qs.filter(default_region_id=region_filter)
        schools = list(schools_qs)

        core_features = self._resolve_guard_feature_codes()

        rules_qs = RegionFeatureCompliance.objects.all()
        if region_filter:
            rules_qs = rules_qs.filter(region_id=region_filter)
        rules_by_region: dict[str, dict[str, str]] = defaultdict(dict)
        for row in rules_qs.values("region_id", "feature_code", "status"):
            rules_by_region[str(row["region_id"])][str(row["feature_code"])] = str(
                row["status"]
            )

        pending_waiver_by_school: dict[str, int] = defaultdict(int)
        waiver_qs = WaiverRequest.objects.filter(status=WaiverRequest.Status.PENDING)
        if region_filter:
            waiver_qs = waiver_qs.filter(school__default_region_id=region_filter)
        for row in waiver_qs.values("school_id").annotate(
            total_count=models.Count("id")
        ):
            pending_waiver_by_school[str(row["school_id"])] = int(row["total_count"])

        school_results: list[SchoolComplianceResult] = []
        for school in schools:
            school_results.append(
                self._build_school_scorecard(
                    school=school,
                    pending_waiver_count=pending_waiver_by_school.get(
                        str(school.pk), 0
                    ),
                    core_features=core_features,
                    rule_lookup=rules_by_region,
                )
            )

        region_rollup: dict[str, dict] = {}
        for school in schools:
            region_code = str(getattr(school, "default_region_id", "") or "UNASSIGNED")
            bucket = region_rollup.setdefault(
                region_code,
                {
                    "schools": 0,
                    "average_score": 0.0,
                    "core_feature_missing_count": 0,
                    "core_feature_missing": [],
                },
            )
            bucket["schools"] += 1
            region_rules = rules_by_region.get(region_code, {})
            missing = [code for code in core_features if code not in region_rules]
            bucket["core_feature_missing_count"] = len(missing)
            bucket["core_feature_missing"] = missing

        for region_code, bucket in region_rollup.items():
            scores = [
                item.score for item in school_results if item.region_code == region_code
            ]
            bucket["average_score"] = (
                round(sum(scores) / len(scores), 2) if scores else 0.0
            )

        global_checks = [
            {
                "check": "waiver_requests_pending_global",
                "value": int(waiver_qs.count()),
                "ok": int(waiver_qs.count()) < 100,
            },
            {
                "check": "region_feature_compliance_rules_total",
                "value": int(rules_qs.count()),
                "ok": int(rules_qs.count()) > 0,
            },
            {
                "check": "schools_without_region",
                "value": int(
                    sum(1 for s in schools if not getattr(s, "default_region_id", None))
                ),
                "ok": int(
                    sum(1 for s in schools if not getattr(s, "default_region_id", None))
                )
                == 0,
            },
        ]

        global_score = self._score_from_checks(global_checks)
        school_average = (
            round(sum(item.score for item in school_results) / len(school_results), 2)
            if school_results
            else 100.0
        )
        overall_score = round((global_score * 0.4) + (school_average * 0.6), 2)

        payload = {
            "score": overall_score,
            "global_score": global_score,
            "school_average_score": school_average,
            "checks": global_checks,
            "regions": region_rollup,
            "schools": [
                {
                    "school_id": item.school_id,
                    "school_slug": item.school_slug,
                    "region_code": item.region_code,
                    "score": item.score,
                    "checks": item.checks,
                }
                for item in school_results
            ],
        }

        if strict and overall_score < min_score:
            if as_json:
                self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            raise CommandError(
                f"Compliance score {overall_score}% is below minimum {min_score}%."
            )

        if as_json:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        self.stdout.write("Compliance Auditor")
        self.stdout.write(f"Overall score: {overall_score}%")
        self.stdout.write(f"Global checks score: {global_score}%")
        self.stdout.write(f"Average school score: {school_average}%")
        for check in global_checks:
            status = "ok" if check.get("ok") else "fail"
            self.stdout.write(f"  - {check['check']}: {status} ({check['value']})")
        for region_code, data in sorted(region_rollup.items()):
            self.stdout.write(
                f"  - region={region_code} schools={data['schools']} "
                f"avg={data['average_score']} missing_core={data['core_feature_missing_count']}"
            )
