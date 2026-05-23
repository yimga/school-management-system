"""
Management command — populate CountryRegistry + CalendarSystemRegistry from
the country-localization seed (apps/siteconfig/_seed_country_localization.py).

Idempotent: uses ``update_or_create`` so re-running is safe. Existing
operator-modified rows are preserved (only registry-managed fields update).

Usage::

    python manage.py seed_country_localization_registries [--dry-run] [--quiet]

After this runs, operators can override per-row via Django admin at
``/admin/registries/countryregistry/`` and ``/admin/registries/calendarsystemregistry/``
to fine-tune the country pack for their tenant population (e.g. translate
``CalendarSystemRegistry.name`` for one specific locale, override
``CountryRegistry.default_terminology_pack`` for a tenant's preferred
terminology pack).

The Wave 1 lookup service (country_localization_service.py) still reads
from the in-memory seed for the hot path (sub-millisecond signup-form
adapter); the DB rows are the operator-override surface, not the runtime
path. A future wave can layer DB overrides on top of the in-memory cascade.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Bulk-seed CountryRegistry + CalendarSystemRegistry from country localization seed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be inserted/updated without writing.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress per-row output; only print summary.",
        )

    def handle(self, *args, **opts):
        dry_run: bool = opts.get("dry_run", False)
        quiet: bool = opts.get("quiet", False)

        from apps.registries.models import (
            CalendarSystemRegistry,
            CountryRegistry,
        )
        from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
        from apps.siteconfig.country_localization_service import resolve_country_pack
        from apps.siteconfig.localization_context_processor import (
            _DEFAULT_CURRENCY_BY_COUNTRY,
            _RTL_COUNTRIES,
        )

        # Country name lookup — pycountry if available, else seed only.
        try:
            import pycountry  # type: ignore
            def country_name(cc: str) -> str:
                c = pycountry.countries.get(alpha_2=cc)
                return c.name if c else cc
        except ImportError:
            def country_name(cc: str) -> str:
                return cc

        # Country -> default language fallback (best effort; operators can override).
        _DEFAULT_LANG_BY_COUNTRY = {
            "FR": "fr", "DE": "de", "ES": "es", "IT": "it", "PT": "pt",
            "NL": "nl", "BE": "fr", "CH": "de", "AT": "de",
            "JP": "ja", "KR": "ko", "CN": "zh-Hans", "TW": "zh-Hant",
            "HK": "zh-Hant", "MO": "pt", "AE": "ar", "SA": "ar",
            "EG": "ar", "MA": "ar", "TN": "ar", "DZ": "ar",
            "IL": "he", "IR": "fa", "AF": "fa", "ET": "am",
            "RU": "ru", "UA": "uk", "TR": "tr",
            "BR": "pt", "MX": "es", "AR": "es", "CL": "es", "CO": "es",
        }

        countries_created = 0
        countries_updated = 0
        calendars_created = 0
        calendars_updated = 0

        with transaction.atomic():
            for cc, pack in COUNTRY_LOCALIZATION.items():
                cc = str(cc).upper()
                resolved = resolve_country_pack(cc)

                cal_systems = resolved.get("calendar_systems") or []
                default_cal_code = ""
                for cal in cal_systems:
                    if cal.get("is_default") or default_cal_code == "":
                        default_cal_code = str(cal.get("code") or "")
                    if cal.get("is_default"):
                        break

                country_defaults = {
                    "name": country_name(cc),
                    "default_language": _DEFAULT_LANG_BY_COUNTRY.get(cc, "en"),
                    "default_currency": _DEFAULT_CURRENCY_BY_COUNTRY.get(cc, "USD"),
                    "default_calendar_family": default_cal_code,
                    "writing_direction": "rtl" if cc in _RTL_COUNTRIES else "ltr",
                    "is_active": True,
                }
                if dry_run:
                    if not quiet:
                        self.stdout.write(f"DRY-RUN country {cc}: {country_defaults['name']}")
                    countries_created += 1
                else:
                    obj, created = CountryRegistry.objects.update_or_create(
                        code=cc, defaults=country_defaults,
                    )
                    if created:
                        countries_created += 1
                    else:
                        countries_updated += 1
                    if not quiet:
                        verb = "CREATE" if created else "UPDATE"
                        self.stdout.write(f"  {verb} country {cc}: {obj.name}")

                # Calendar systems.
                for cal in cal_systems:
                    cal_code = str(cal.get("code") or "").strip()
                    if not cal_code:
                        continue
                    cal_defaults = {
                        "name": str(cal.get("label") or cal_code)[:120],
                        "country_code": cc,
                        "term_count_per_year": int(cal.get("term_count") or 3),
                        "metadata": {
                            "term_names": list(cal.get("term_names") or []),
                            "week_start": int(cal.get("week_start") or 1),
                            "academic_year_starts_month": int(
                                cal.get("academic_year_starts_month") or 1
                            ),
                            "is_default": bool(cal.get("is_default")),
                            "has_half_terms": bool(cal.get("has_half_terms")),
                        },
                        "is_active": True,
                    }
                    if dry_run:
                        calendars_created += 1
                    else:
                        cal_obj, created = CalendarSystemRegistry.objects.update_or_create(
                            code=cal_code, defaults=cal_defaults,
                        )
                        if created:
                            calendars_created += 1
                        else:
                            calendars_updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nseed_country_localization_registries: complete\n"
            f"  Countries: {countries_created} created, {countries_updated} updated\n"
            f"  Calendars: {calendars_created} created, {calendars_updated} updated"
            + ("  [DRY-RUN]" if dry_run else "")
        ))
