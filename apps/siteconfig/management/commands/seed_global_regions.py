from django.core.management.base import BaseCommand
from django.db import transaction

from apps.siteconfig.education_profile_engine import ensure_country_profile
from apps.siteconfig.global_catalog import GlobalGeoCatalog
from apps.siteconfig.models import RegionConfig

# Comma-decimal + non-breaking-space thousands is the francophone number
# convention ("12 500,50"), the CFA-franc zone standard. Seed it so a Cameroon /
# Senegal tenant renders numbers the way its users read them instead of the
# en-style "12,500.50". Keyed off the CFA currencies (which ARE the francophone-
# Africa set) plus the francophone-euro/comoros countries, so it is correct even
# where a bilingual country's catalog default_language is recorded as English.
_FR_NUMBER_CURRENCIES = frozenset({"XAF", "XOF"})
_FR_NUMBER_COUNTRIES = frozenset({"FR", "BE", "LU", "MC", "MG", "DJ", "KM"})
_FR_DECIMAL_SEP = ","
_FR_THOUSANDS_SEP = "\xa0"  # non-breaking space


def _number_separators(code, currency, default_language) -> tuple[str, str]:
    is_fr = (
        currency in _FR_NUMBER_CURRENCIES
        or code in _FR_NUMBER_COUNTRIES
        or (default_language or "").split("-")[0].lower() == "fr"
    )
    return (_FR_DECIMAL_SEP, _FR_THOUSANDS_SEP) if is_fr else (".", ",")


class Command(BaseCommand):
    help = "Seed RegionConfig for all countries from the global catalog."

    def add_arguments(self, parser):
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Also update timezone/language/currency for existing regions.",
        )
        parser.add_argument(
            "--with-profiles",
            action="store_true",
            help="Also seed a baseline education profile pack for each country (sub-system ANY).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        update_existing = bool(options.get("update_existing"))
        with_profiles = bool(options.get("with_profiles"))
        countries = GlobalGeoCatalog.list_countries()
        if not countries:
            self.stdout.write(
                self.style.ERROR(
                    "Global catalog unavailable. Install pycountry + geonamescache."
                )
            )
            return

        created_count = 0
        updated_count = 0
        profile_count = 0
        for country in countries:
            code = country["code"]
            defaults = GlobalGeoCatalog.country_defaults(code)
            dec_sep, thou_sep = _number_separators(
                code, defaults["currency"], defaults["default_language"]
            )
            region, created = RegionConfig.objects.get_or_create(
                code=code,
                defaults={
                    "name": defaults["country_name"],
                    "default_language": defaults["default_language"],
                    "timezone": defaults["timezone"] or "UTC",
                    "date_format": "DD/MM/YYYY",
                    "grading_scale": "0-100",
                    "default_currency": defaults["currency"],
                    "decimal_separator": dec_sep,
                    "thousands_separator": thou_sep,
                    "academic_year_start_month": 9,
                    "term_count_per_year": 3,
                },
            )
            if created:
                created_count += 1
                continue

            if not update_existing:
                continue

            changed = False
            if defaults["country_name"] and region.name != defaults["country_name"]:
                region.name = defaults["country_name"]
                changed = True
            if defaults["timezone"] and region.timezone != defaults["timezone"]:
                region.timezone = defaults["timezone"]
                changed = True
            if (
                defaults["default_language"]
                and region.default_language != defaults["default_language"]
            ):
                region.default_language = defaults["default_language"]
                changed = True
            if defaults["currency"] and region.default_currency != defaults["currency"]:
                region.default_currency = defaults["currency"]
                changed = True
            if region.decimal_separator != dec_sep:
                region.decimal_separator = dec_sep
                changed = True
            if region.thousands_separator != thou_sep:
                region.thousands_separator = thou_sep
                changed = True

            if changed:
                region.save(
                    update_fields=[
                        "name",
                        "timezone",
                        "default_language",
                        "default_currency",
                        "decimal_separator",
                        "thousands_separator",
                        "updated_at",
                    ]
                )
                updated_count += 1
            if with_profiles:
                profile = ensure_country_profile(region=region, sub_system="ANY")
                if profile is not None:
                    profile_count += 1

        summary = (
            f"Global region seed complete. Created={created_count}, "
            f"Updated={updated_count}, Total={len(countries)}"
        )
        if with_profiles:
            summary += f", Profiles={profile_count}"
        self.stdout.write(self.style.SUCCESS(summary))
