from __future__ import annotations

import json
from pathlib import Path
import tempfile

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, ProgrammingError

from apps.siteconfig.models import ThemePack


class Command(BaseCommand):
    help = (
        "Import a UI parity fixture (ThemePack + SiteSettings) and normalize defaults."
    )

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

        ThemePack and SiteSettings live in the shared/public schema when
        USE_DJANGO_TENANTS=1, so importing per tenant leaves the control-plane UI
        config stale and breaks parity checks. Keep the import scoped to the
        current schema and let deploy/runtime choose the correct connection.
        """
        normalized_data = self._normalize_fixture_fields(data)
        self._ensure_dependencies(normalized_data)
        self._clear_themepack_default_before_load()
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", delete=False
        ) as tmp:
            tmp.write(json.dumps(normalized_data, indent=2, ensure_ascii=False))
            tmp.write("\n")
            temp_path = tmp.name
        try:
            call_command("loaddata", temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)
        if not options["skip_normalize"]:
            call_command("normalize_ui_config")

    def _clear_themepack_default_before_load(self) -> None:
        """Clear is_default on all ThemePacks so loaddata can set the fixture's default without violating the single-default constraint."""
        updated = ThemePack.objects.filter(is_default=True).update(is_default=False)
        if updated:
            self.stdout.write(
                f"Cleared is_default on {updated} ThemePack(s) before load."
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
        for row in normalized:
            if (
                not isinstance(row, dict)
                or row.get("model") != "siteconfig.sitesettings"
            ):
                continue
            fields = row.get("fields") or {}
            if "compliance_profile" in fields and "compliance_profile_id" not in fields:
                fields["compliance_profile_id"] = fields.pop("compliance_profile")
        return normalized
