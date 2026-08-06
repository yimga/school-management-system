"""Coverage guards for the localization reference registries.

The TimeZone / Locale / InstitutionType / CalendarSystem registries previously
had NO production seeder (only test fixtures wrote them), so a live/fresh
database left them empty and every school with those fields set showed a
permanent "yellow triangle" on the Launch/Setup registry-alignment card.

These lock the new seeders (single source of truth in
``apps.registries.services``) and the lazy self-heal on the Launch snapshot.
"""

from __future__ import annotations

from django.test import TestCase

from apps.registries.models import (
    CalendarSystemRegistry,
    InstitutionTypeRegistry,
    LocaleRegistry,
    TimeZoneRegistry,
)
from apps.registries.services import (
    CALENDAR_SYSTEM_SEED_DEFAULTS,
    INSTITUTION_TYPE_SEED_DEFAULTS,
    LOCALE_SEED_DEFAULTS,
    ensure_calendar_system_registry_seed,
    ensure_institution_type_registry_seed,
    ensure_localization_registry_baseline,
    ensure_locale_registry_seed,
    ensure_timezone_registry_seed,
)


class LocalizationSeedTests(TestCase):
    def _clear(self):
        TimeZoneRegistry.objects.all().delete()
        LocaleRegistry.objects.all().delete()
        InstitutionTypeRegistry.objects.all().delete()
        CalendarSystemRegistry.objects.all().delete()

    def test_baseline_seeds_the_canonical_codes(self):
        self._clear()
        ensure_localization_registry_baseline()

        # school_type defaults to BASE_SCHOOL for every school — it MUST exist.
        self.assertTrue(
            InstitutionTypeRegistry.objects.filter(
                code="BASE_SCHOOL", is_active=True
            ).exists()
        )
        for code in ("TECHNICAL_COLLEGE", "STEM_ACADEMY"):
            self.assertTrue(
                InstitutionTypeRegistry.objects.filter(code=code, is_active=True).exists(),
                code,
            )
        self.assertTrue(
            TimeZoneRegistry.objects.filter(code="UTC", is_active=True).exists()
        )
        self.assertEqual(
            TimeZoneRegistry.objects.get(code="UTC").name, "Coordinated Universal Time"
        )
        self.assertTrue(TimeZoneRegistry.objects.filter(code="Africa/Douala").exists())
        for code in ("en", "fr", "ar"):
            self.assertTrue(
                LocaleRegistry.objects.filter(code=code, is_active=True).exists(), code
            )
        self.assertTrue(LocaleRegistry.objects.get(code="ar").is_rtl)
        self.assertTrue(
            CalendarSystemRegistry.objects.filter(
                code="gregorian", is_active=True
            ).exists()
        )

    def test_seeders_are_idempotent(self):
        self._clear()
        ensure_localization_registry_baseline()
        tz1 = TimeZoneRegistry.objects.count()
        loc1 = LocaleRegistry.objects.count()
        inst1 = InstitutionTypeRegistry.objects.count()
        cal1 = CalendarSystemRegistry.objects.count()
        # Re-run: no duplicates (PK is the code, and helpers short-circuit).
        ensure_timezone_registry_seed()
        ensure_locale_registry_seed()
        ensure_institution_type_registry_seed()
        ensure_calendar_system_registry_seed()
        self.assertEqual(TimeZoneRegistry.objects.count(), tz1)
        self.assertEqual(LocaleRegistry.objects.count(), loc1)
        self.assertEqual(InstitutionTypeRegistry.objects.count(), inst1)
        self.assertEqual(CalendarSystemRegistry.objects.count(), cal1)
        self.assertGreaterEqual(loc1, len(LOCALE_SEED_DEFAULTS))
        self.assertGreaterEqual(inst1, len(INSTITUTION_TYPE_SEED_DEFAULTS))
        self.assertGreaterEqual(cal1, len(CALENDAR_SYSTEM_SEED_DEFAULTS))

    def test_launch_snapshot_self_heals_localization_registries(self):
        """Regression: with the localization tables empty, viewing the Launch
        registry snapshot must seed them so the fields align (no yellow
        triangle) instead of reporting 'verify registry seeding'."""
        from apps.schools.models import School
        from apps.setup_studio.services import _registry_alignment_snapshot

        self._clear()
        school = School.objects.create(
            name="Heal School",
            slug="heal-school",
            subdomain="heal-school",
            country_code="CM",
            timezone="Africa/Douala",
            school_type="BASE_SCHOOL",
            is_active=True,
        )
        snap = _registry_alignment_snapshot(school)
        # The self-heal should have created the rows and the fields should align.
        self.assertTrue(snap.get("timezone_registry_ok"))
        self.assertEqual(snap.get("iana_timezone"), "Africa/Douala")
        self.assertTrue(snap.get("institution_type_registry_ok"))
        self.assertEqual(snap.get("institution_type_code"), "BASE_SCHOOL")
