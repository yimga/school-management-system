from __future__ import annotations

import json
from pathlib import Path

from django.core import serializers
from django.core.management.base import BaseCommand, CommandError

from apps.siteconfig.models import SiteSettings, ThemePack


def _canonicalize_optional_blank_fields(records: list[dict]) -> list[dict]:
    for row in records:
        if not isinstance(row, dict):
            continue
        fields = row.get("fields") or {}
        if row.get("model") == "siteconfig.themepack":
            if fields.get("backend_console_theme", None) == "":
                fields.pop("backend_console_theme", None)
            continue
        if (
            row.get("model") == "siteconfig.sitesettings"
            and "compliance_profile_id" in fields
        ):
            fields["compliance_profile"] = fields.pop("compliance_profile_id")
    return records


class Command(BaseCommand):
    help = "Export ThemePack + SiteSettings as a JSON fixture for dev/live UI parity."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="fixtures/ui_config.json",
            help="Output JSON fixture path (default: fixtures/ui_config.json).",
        )

    def handle(self, *args, **options):
        output_path = Path(options["output"])
        site_settings = list(SiteSettings.objects.order_by("pk"))
        theme_packs = list(ThemePack.objects.order_by("pk"))
        if not site_settings:
            raise CommandError("No SiteSettings row found; cannot export UI config.")
        if not theme_packs:
            raise CommandError("No ThemePack rows found; cannot export UI config.")

        records = theme_packs + site_settings
        payload = serializers.serialize("json", records, indent=2)
        decoded = json.loads(payload)
        if not isinstance(decoded, list) or not decoded:
            raise CommandError("Serialization produced an empty payload.")
        decoded = _canonicalize_optional_blank_fields(decoded)
        payload = json.dumps(decoded, indent=2, ensure_ascii=False)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported UI config: {len(theme_packs)} ThemePacks + {len(site_settings)} "
                f"SiteSettings -> {output_path}"
            )
        )
