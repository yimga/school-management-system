from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.siteconfig.models import SiteSettings, ThemePack


THEME_COMPARE_FIELDS = (
    "name",
    "slug",
    "primary_color",
    "accent_color",
    "background_color",
    "layout",
    "applies_to_admin",
    "backend_console_theme",
    "is_active",
    "is_default",
)

SITE_COMPARE_FIELDS = (
    "theme_pack",
    "admin_theme_pack",
    "primary_color",
    "accent_color",
    "theme_brightness",
    "backend_console_theme",
    "use_dark_mode",
    "admin_use_site_primary",
    "default_term_report_style",
    "default_annual_report_style",
    "layout_style",
    "base_font_size",
    "default_refresh_rate",
)

SITE_FOREIGN_KEY_FIELDS = frozenset(
    {
        "theme_pack",
        "admin_theme_pack",
        "default_term_report_style",
        "default_annual_report_style",
    }
)

BLANK_EQUALS_NULL_FIELDS = frozenset(
    {
        "backend_console_theme",
    }
)


def _normalize(value: Any, field_name: str | None = None) -> Any:
    if field_name in BLANK_EQUALS_NULL_FIELDS and value in ("", None):
        return None
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    if isinstance(value, list):
        return json.dumps(value)
    return value


class Command(BaseCommand):
    help = (
        "Verify current SiteSettings/ThemePack values match a UI fixture "
        "(default: fixtures/ui_config.json)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--input-file",
            default="fixtures/ui_config.json",
            help="Input fixture path (default: fixtures/ui_config.json).",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail with non-zero exit code when mismatches are detected.",
        )

    def handle(self, *args, **options):
        fixture_path = Path(options["input_file"])
        strict = bool(options.get("strict"))
        fixture_theme_rows, fixture_site_row = self._load_fixture(fixture_path)

        mismatches: list[str] = []
        db_themes = {theme.pk: theme for theme in ThemePack.objects.order_by("pk")}

        missing_theme_ids = sorted(set(fixture_theme_rows.keys()) - set(db_themes.keys()))
        extra_theme_ids = sorted(set(db_themes.keys()) - set(fixture_theme_rows.keys()))
        if missing_theme_ids:
            mismatches.append(
                "Missing ThemePack rows in DB: " + ", ".join(str(pk) for pk in missing_theme_ids)
            )
        if extra_theme_ids:
            mismatches.append(
                "Extra ThemePack rows in DB: " + ", ".join(str(pk) for pk in extra_theme_ids)
            )

        for theme_id, fixture_fields in sorted(fixture_theme_rows.items()):
            theme = db_themes.get(theme_id)
            if not theme:
                continue
            for field_name in THEME_COMPARE_FIELDS:
                expected = _normalize(fixture_fields.get(field_name), field_name)
                actual = _normalize(getattr(theme, field_name, None), field_name)
                if expected != actual:
                    mismatches.append(
                        f"ThemePack[{theme_id}].{field_name}: fixture={expected!r}, db={actual!r}"
                    )

        site = SiteSettings.objects.order_by("pk").first()
        if not site:
            raise CommandError("No SiteSettings row found in database.")

        for field_name in SITE_COMPARE_FIELDS:
            fixture_value = fixture_site_row.get(field_name)
            if field_name in SITE_FOREIGN_KEY_FIELDS:
                actual_value = getattr(site, f"{field_name}_id", None)
            else:
                actual_value = getattr(site, field_name, None)

            expected = _normalize(fixture_value, field_name)
            actual = _normalize(actual_value, field_name)
            if expected != actual:
                mismatches.append(
                    f"SiteSettings.{field_name}: fixture={expected!r}, db={actual!r}"
                )

        if mismatches:
            self.stdout.write(self.style.WARNING("UI parity mismatches detected:"))
            for item in mismatches:
                self.stdout.write(f"- {item}")
            if strict:
                raise CommandError(
                    f"UI parity check failed with {len(mismatches)} mismatch(es)."
                )
            self.stdout.write(
                self.style.WARNING(
                    "Run with --strict in CI/release gates to fail on mismatch."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"UI parity check passed ({len(fixture_theme_rows)} ThemePacks + 1 SiteSettings)."
            )
        )

    def _load_fixture(self, input_path: Path) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
        if not input_path.exists():
            raise CommandError(f"Fixture not found: {input_path}")
        raw = input_path.read_text(encoding="utf-8").strip()
        if not raw:
            raise CommandError(f"Fixture is empty: {input_path}")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in fixture: {exc}") from exc

        if not isinstance(payload, list) or not payload:
            raise CommandError("Fixture must be a non-empty JSON list.")

        theme_rows: dict[int, dict[str, Any]] = {}
        site_row: dict[str, Any] | None = None
        for row in payload:
            if not isinstance(row, dict):
                continue
            model = row.get("model")
            pk = row.get("pk")
            fields = row.get("fields") or {}
            if model == "siteconfig.themepack" and pk is not None:
                theme_rows[int(pk)] = fields
            elif model == "siteconfig.sitesettings" and site_row is None:
                site_row = fields

        if not theme_rows:
            raise CommandError("Fixture has no siteconfig.themepack rows.")
        if site_row is None:
            raise CommandError("Fixture has no siteconfig.sitesettings row.")
        return theme_rows, site_row
