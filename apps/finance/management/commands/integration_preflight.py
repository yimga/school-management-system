from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.api.ministry_connectors import ministry_runtime_status
from apps.finance.ocr_runtime import get_ocr_runtime_status
from apps.platform_runtime.config_resolver import get_effective_config
from apps.siteconfig.models import default_backend_feature_flags


class Command(BaseCommand):
    help = "Check OCR + Ministry integration runtime readiness."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output structured JSON only.",
        )

    def handle(self, *args, **options):
        flags = {
            **default_backend_feature_flags(),
            **(get_effective_config(key="backend_feature_flags") or {}),
        }

        ocr_method = (
            get_effective_config(
                key="finance_receipt_verification_method", default="pattern"
            )
            or "pattern"
        )
        ocr_status = get_ocr_runtime_status(
            verification_method=ocr_method,
            marksheet_ocr_command=get_effective_config(
                key="marksheet_ocr_command", default=""
            ),
        )
        ministry_status = ministry_runtime_status()

        result = {
            "ocr": {
                "feature_enabled": bool(flags.get("enable_ocr_scan_teller")),
                "method": ocr_method,
                "status": ocr_status,
            },
            "ministry": {
                "cartescolaire_feature_enabled": bool(
                    flags.get("enable_ministry_api_cartescolaire")
                ),
                "dgi_feature_enabled": bool(flags.get("enable_ministry_api_dgi")),
                "live_sync_feature_enabled": bool(
                    flags.get("enable_ministry_live_sync")
                ),
                "status": ministry_status,
            },
        }

        if options.get("json"):
            self.stdout.write(json.dumps(result, indent=2))
        else:
            self.stdout.write(self.style.MIGRATE_HEADING("Integration preflight"))
            self.stdout.write(
                f"OCR: feature={'ON' if result['ocr']['feature_enabled'] else 'OFF'} "
                f"method={ocr_method} ready={bool(ocr_status.get('ready'))}"
            )
            if ocr_status.get("missing"):
                self.stdout.write(f"  Missing: {'; '.join(ocr_status['missing'])}")

            self.stdout.write(
                "Ministry: "
                f"cartescolaire={'ON' if result['ministry']['cartescolaire_feature_enabled'] else 'OFF'} "
                f"dgi={'ON' if result['ministry']['dgi_feature_enabled'] else 'OFF'} "
                f"live_sync={'ON' if result['ministry']['live_sync_feature_enabled'] else 'OFF'} "
                f"mode={ministry_status.get('mode')}"
            )
            if ministry_status.get("cartescolaire", {}).get("missing"):
                self.stdout.write(
                    "  Cartescolaire missing: "
                    + ", ".join(ministry_status["cartescolaire"]["missing"])
                )
            if ministry_status.get("dgi", {}).get("missing"):
                self.stdout.write(
                    "  DGI missing: " + ", ".join(ministry_status["dgi"]["missing"])
                )

        # Fail only when feature is enabled but runtime is not ready.
        has_blocker = False
        if result["ocr"]["feature_enabled"] and not bool(ocr_status.get("ready")):
            has_blocker = True
        if result["ministry"]["live_sync_feature_enabled"]:
            if (
                result["ministry"]["cartescolaire_feature_enabled"]
                and not ministry_status["cartescolaire"]["ready"]
            ):
                has_blocker = True
            if (
                result["ministry"]["dgi_feature_enabled"]
                and not ministry_status["dgi"]["ready"]
            ):
                has_blocker = True

        if has_blocker:
            self.stderr.write(
                self.style.ERROR(
                    "Integration preflight failed: runtime blockers found."
                )
            )
            raise SystemExit(2)
