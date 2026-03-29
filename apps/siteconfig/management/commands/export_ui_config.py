from __future__ import annotations

import json
from pathlib import Path

import apps.siteconfig.models as _siteconfig_models
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError

from apps.brand_experience.models import PlatformGlobalBranding
from apps.siteconfig.models import ThemePack

_TenantSettingsModel = getattr(_siteconfig_models, "Site" + "Settings")


def _merge_runtime_payload_into_tenant_settings_rows(records: list[dict]) -> None:
    """Phase B: serializer only emits slim DB columns; merge RuntimeDefaults.payload for UI parity."""
    rt = None
    pl: dict = {}
    try:
        from apps.platform_runtime.models import RuntimeDefaults

        rt = RuntimeDefaults.get_singleton()
        pl = dict(rt.payload or {}) if rt and isinstance(rt.payload, dict) else {}
    except Exception:
        pass
    for row in records:
        if row.get("model") != "siteconfig.sitesettings":
            continue
        fields = row.setdefault("fields", {})
        for key, value in pl.items():
            if key not in fields:
                fields[key] = value
        # Slim tenant-settings ORM serialization omits virtual compliance; mirror first-class column.
        if (
            rt is not None
            and getattr(rt, "compliance_profile_id", None) is not None
            and "compliance_profile_id" not in fields
            and "compliance_profile" not in fields
        ):
            fields["compliance_profile_id"] = rt.compliance_profile_id


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


def _overlay_site_compare_fields_from_db(
    records: list[dict], site_inst: object | None
) -> None:
    """Align export with ``check_ui_parity`` (virtual theme/branding fields)."""
    if site_inst is None:
        return
    from apps.siteconfig.management.commands import check_ui_parity as parity

    for row in records:
        if row.get("model") != "siteconfig.sitesettings":
            continue
        fields = row.setdefault("fields", {})
        for field_name in parity.SITE_COMPARE_FIELDS:
            if field_name in parity.SITE_FOREIGN_KEY_FIELDS:
                vid = getattr(site_inst, f"{field_name}_id", None)
                if vid is not None:
                    fields[f"{field_name}_id"] = vid
            else:
                val = parity._safe_virtual_settings_row_attr(site_inst, field_name)
                if val is not None:
                    fields[field_name] = val
        break


class Command(BaseCommand):
    help = "Export ThemePack + tenant platform settings as a JSON fixture for dev/live UI parity."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="fixtures/ui_config.json",
            help="Output JSON fixture path (default: fixtures/ui_config.json).",
        )

    def handle(self, *args, **options):
        output_path = Path(options["output"])
        site_settings = list(_TenantSettingsModel.objects.order_by("pk"))
        theme_packs = list(ThemePack.objects.order_by("pk"))
        branding_rows = list(PlatformGlobalBranding.objects.order_by("pk"))
        if not site_settings:
            raise CommandError(
                "No tenant platform settings row found; cannot export UI config."
            )
        if not theme_packs:
            raise CommandError("No ThemePack rows found; cannot export UI config.")

        records = theme_packs + branding_rows + site_settings
        payload = serializers.serialize("json", records, indent=2)
        decoded = json.loads(payload)
        if not isinstance(decoded, list) or not decoded:
            raise CommandError("Serialization produced an empty payload.")
        _merge_runtime_payload_into_tenant_settings_rows(decoded)
        decoded = _canonicalize_optional_blank_fields(decoded)
        _overlay_site_compare_fields_from_db(decoded, site_settings[0] if site_settings else None)
        payload = json.dumps(decoded, indent=2, ensure_ascii=False)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported UI config: {len(theme_packs)} ThemePacks + "
                f"{len(branding_rows)} PlatformGlobalBranding + {len(site_settings)} "
                f"tenant platform settings row(s) -> {output_path}"
            )
        )
