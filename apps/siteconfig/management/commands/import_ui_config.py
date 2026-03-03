from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, ProgrammingError


class Command(BaseCommand):
    help = "Import a UI parity fixture (ThemePack + SiteSettings) and normalize defaults."

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
            raise CommandError(f"Fixture must contain a non-empty JSON list: {input_path}")

        models_present = {row.get("model") for row in data if isinstance(row, dict)}
        required_models = {"siteconfig.themepack", "siteconfig.sitesettings"}
        missing = required_models - models_present
        if missing:
            raise CommandError(
                f"Fixture missing required model entries: {', '.join(sorted(missing))}"
            )

        if getattr(settings, "USE_DJANGO_TENANTS", False):
            self._import_per_tenant(data, input_path, options)
        else:
            self._ensure_dependencies(data)
            call_command("loaddata", str(input_path))
            if not options["skip_normalize"]:
                call_command("normalize_ui_config")
        self.stdout.write(self.style.SUCCESS(f"Imported UI config from {input_path}"))

    def _import_per_tenant(self, data: list, input_path: Path, options: dict) -> None:
        """Run ensure_dependencies + loaddata + normalize in each tenant schema (avoids public schema)."""
        from django_tenants.utils import tenant_context

        from apps.customers.models import Client

        clients = list(Client.objects.all().order_by("id"))
        if not clients:
            self.stdout.write(self.style.WARNING("No tenants (Clients) found; skipping import."))
            return
        for client in clients:
            schema = getattr(client, "schema_name", None) or ""
            self.stdout.write(f"Importing into tenant: {schema!r} ({client.name})")
            with tenant_context(client):
                self._ensure_dependencies(data)
                call_command("loaddata", str(input_path))
                if not options.get("skip_normalize"):
                    call_command("normalize_ui_config")

    def _ensure_dependencies(self, data: list[dict]) -> None:
        """Create required FK rows that may be missing in fresh/local databases."""
        compliance_ids: set[int] = set()
        for row in data:
            if not isinstance(row, dict):
                continue
            if row.get("model") != "siteconfig.sitesettings":
                continue
            fields = row.get("fields") or {}
            profile_id = fields.get("compliance_profile")
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
