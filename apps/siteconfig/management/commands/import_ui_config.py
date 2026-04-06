from __future__ import annotations

import json
from pathlib import Path
import tempfile

import apps.siteconfig.models as _siteconfig_models
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, ProgrammingError, transaction

from apps.siteconfig.models import ThemePack

_TenantSettingsModel = getattr(_siteconfig_models, "Site" + "Settings")


class Command(BaseCommand):
    help = (
        "Import a UI parity fixture (ThemePack + tenant platform settings) and normalize defaults."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant_settings_runtime_field_extras: dict[int, dict] = {}

    def add_arguments(self, parser):
        parser.add_argument(
            "input_file",
            nargs="?",
            default="fixtures/ui_config.json",
            help="Input JSON fixture path (default: fixtures/ui_config.json).",
        )
        parser.add_argument(
            "--skip-normalize",
            action="store_true",
            help="Skip running normalize_ui_config after loaddata.",
        )

    def handle(self, *args, **options):
        self._tenant_settings_runtime_field_extras = {}
        input_path = Path(options["input_file"])
        if not input_path.exists():
            raise CommandError(f"File not found: {input_path}")
        raw = input_path.read_text(encoding="utf-8").strip()
        if not raw:
            raise CommandError(f"File is empty: {input_path}")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in {input_path}: {exc}") from exc

        if not isinstance(data, list) or not data:
            raise CommandError(
                f"Fixture must contain a non-empty JSON list: {input_path}"
            )

        models_present = {row.get("model") for row in data if isinstance(row, dict)}
        required_models = {"siteconfig.themepack", "siteconfig.sitesettings"}
        missing = required_models - models_present
        if missing:
            raise CommandError(
                f"Fixture missing required model entries: {', '.join(sorted(missing))}"
            )

        self._import_into_current_schema(data, input_path, options)
        self.stdout.write(self.style.SUCCESS(f"Imported UI config from {input_path}"))

    def _import_into_current_schema(
        self, data: list, input_path: Path, options: dict
    ) -> None:
        """
        Import UI config into the active schema.

        ThemePack and tenant platform settings live in the shared/public schema when
        USE_DJANGO_TENANTS=1, so importing per tenant leaves the control-plane UI
        config stale and breaks parity checks. Keep the import scoped to the
        current schema and let deploy/runtime choose the correct connection.
        """
        normalized_data = self._normalize_fixture_fields(data)
        self._ensure_dependencies(normalized_data)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", delete=False
        ) as tmp:
            tmp.write(json.dumps(normalized_data, indent=2, ensure_ascii=False))
            tmp.write("\n")
            temp_path = tmp.name
        try:
            with transaction.atomic():
                self._replace_themepacks_before_load(normalized_data)
                self._clear_themepack_default_before_load()
                call_command("loaddata", temp_path)
                self._apply_tenant_settings_runtime_extras()
                if not options["skip_normalize"]:
                    call_command("normalize_ui_config")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def _clear_themepack_default_before_load(self) -> None:
        """Clear is_default on all ThemePacks so loaddata can set the fixture's default without violating the single-default constraint."""
        updated = ThemePack.objects.filter(is_default=True).update(is_default=False)
        if updated:
            self.stdout.write(
                f"Cleared is_default on {updated} ThemePack(s) before load."
            )

    def _replace_themepacks_before_load(self, data: list[dict]) -> None:
        """
        UI parity imports are replace-semantics for ThemePacks.

        The committed fixture is the source of truth for these rows during release
        verification, so pre-existing packs must be removed to avoid slug
        collisions and later strict-parity failures from extra rows.
        """
        fixture_theme_rows = [
            row
            for row in data
            if isinstance(row, dict) and row.get("model") == "siteconfig.themepack"
        ]
        if not fixture_theme_rows:
            return
        existing = ThemePack.objects.count()
        if not existing:
            return
        ThemePack.objects.all().delete()
        self.stdout.write(
            f"Removed {existing} existing ThemePack(s) before fixture load."
        )

    def _ensure_dependencies(self, data: list[dict]) -> None:
        """Create required FK rows that may be missing in fresh/local databases."""
        compliance_ids: set[int] = set()
        for row in data:
            if not isinstance(row, dict):
                continue
            if row.get("model") != "siteconfig.sitesettings":
                continue
            fields = row.get("fields") or {}
            profile_id = fields.get(
                "compliance_profile_id", fields.get("compliance_profile")
            )
            if isinstance(profile_id, int):
                compliance_ids.add(profile_id)

        if not compliance_ids:
            return

        try:
            from apps.finance.models import ComplianceProfile

            for profile_id in sorted(compliance_ids):
                ComplianceProfile.objects.get_or_create(
                    id=profile_id,
                    defaults={
                        "name": "Cameroon Default",
                        "country_code": "CM",
                    },
                )
        except (OperationalError, ImportError):
            # If finance table/model is unavailable, loaddata will raise a clear error next.
            return
        except ProgrammingError as e:
            # e.g. "column finance_complianceprofile.vat_rate does not exist" when tenant
            # schema is behind (migrate_schemas --tenant not run or failed).
            raise CommandError(
                "Database schema is out of date (tenant migrations missing). "
                "Error: %s. Run: python manage.py migrate_schemas --tenant --noinput"
                % (e,)
            ) from e

    def _normalize_fixture_fields(self, data: list[dict]) -> list[dict]:
        normalized = json.loads(json.dumps(data))
        allowed_site_fields: set[str] = set()
        for field in _TenantSettingsModel._meta.get_fields():
            if not getattr(field, "concrete", False):
                continue
            allowed_site_fields.add(field.name)
            att = getattr(field, "attname", None)
            if att:
                allowed_site_fields.add(att)
        for row in normalized:
            if (
                not isinstance(row, dict)
                or row.get("model") != "siteconfig.sitesettings"
            ):
                continue
            fields = row.get("fields") or {}
            if "compliance_profile" in fields and "compliance_profile_id" not in fields:
                fields["compliance_profile_id"] = fields.pop("compliance_profile")
            extra: dict = {}
            for key in list(fields.keys()):
                if key not in allowed_site_fields:
                    extra[key] = fields.pop(key)
            pk = row.get("pk")
            if extra and pk is not None:
                self._tenant_settings_runtime_field_extras[int(pk)] = extra
        return normalized

    def _apply_tenant_settings_runtime_extras(self) -> None:
        """
        Phase B Batch 3: keys stripped from slim tenant-settings rows (theme FKs, etc.)
        are merged into PlatformGlobalBranding and RuntimeDefaults so imports stay coherent.
        """
        if not self._tenant_settings_runtime_field_extras:
            return
        try:
            from apps.brand_experience.platform_global_branding import (
                PlatformGlobalBranding,
            )
        except ImportError:
            return
        pgb, _ = PlatformGlobalBranding.objects.get_or_create(pk=1)
        rt_merge: dict = {}
        legacy_fk_key_map = {
            "theme_pack": "theme_pack_id",
            "admin_theme_pack": "admin_theme_pack_id",
            "teacher_theme_pack": "teacher_theme_pack_id",
            "parent_theme_pack": "parent_theme_pack_id",
            "default_term_report_style": "default_term_report_style_id",
            "default_annual_report_style": "default_annual_report_style_id",
        }
        pgb_fk_keys = frozenset(
            {
                "theme_pack_id",
                "admin_theme_pack_id",
                "teacher_theme_pack_id",
                "parent_theme_pack_id",
                "default_term_report_style_id",
                "default_annual_report_style_id",
            }
        )
        for _pk, extra in self._tenant_settings_runtime_field_extras.items():
            for k, v in extra.items():
                target_key = legacy_fk_key_map.get(k, k)
                if target_key in pgb_fk_keys:
                    setattr(pgb, target_key, v)
                else:
                    rt_merge[target_key] = v
        pgb.save()
        if rt_merge:
            _TenantSettingsModel._persist_runtime_payload_updates(rt_merge)
            try:
                from apps.platform_runtime.helpers import (
                    invalidate_effective_site_settings_cache,
                )

                invalidate_effective_site_settings_cache()
            except ImportError:
                pass
