"""Operational kernel integration tests."""

from __future__ import annotations

from datetime import date
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from apps.evals.grading_formula_engine import (
    PRESET_GRADING_FORMULAS,
    GradingFormulaError,
    evaluate_grading_formula,
)
from apps.metadata.country_eav_catalog import catalog_entries_for_country, seed_country_eav_definitions
from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.schoolops.substitute_market import (
    ShiftAlreadyBooked,
    SubstituteShiftOpenEvent,
    acquire_shift_slot_lock,
    open_shift,
    release_shift_slot_lock,
)


class GradingFormulaEngineTests(TestCase):
    def test_francophone_preset(self):
        result = evaluate_grading_formula(
            formula_text=PRESET_GRADING_FORMULAS["francophone_0_20"],
            variables={"exam": 15.0, "coursework": 12.0},
            scale_key="francophone_0_20",
        )
        self.assertAlmostEqual(result.value, 13.8)

    def test_rejects_code_injection(self):
        with self.assertRaises(GradingFormulaError):
            evaluate_grading_formula(
                formula_text="__import__('os').system('x')",
                variables={},
            )


class CountryEavCatalogTests(TestCase):
    def test_india_aadhaar_catalog(self):
        rows = catalog_entries_for_country("IN")
        keys = {r["field_key"] for r in rows}
        self.assertIn("aadhaar_reference", keys)

    def test_seed_country_definitions(self):
        CountryRegistry.objects.get_or_create(code="IN", defaults={"name": "India"})
        school = School.objects.create(
            name="EAV School",
            slug="eav-school",
            subdomain="eav-school",
            country_code="IN",
            is_active=True,
        )
        stats = seed_country_eav_definitions(school=school, country_code="IN")
        self.assertGreater(stats["created"], 0)


class SubstituteMarketLockTests(TestCase):
    def setUp(self):
        cache.clear()
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Sub School",
            slug="sub-school",
            subdomain="sub-school",
            country_code="CM",
            is_active=True,
        )

    def test_lock_prevents_double_booking(self):
        d = date.today()
        self.assertTrue(acquire_shift_slot_lock(school_id=self.school.pk, work_date=d))
        self.assertFalse(acquire_shift_slot_lock(school_id=self.school.pk, work_date=d))
        release_shift_slot_lock(school_id=self.school.pk, work_date=d)

    def test_open_shift_publishes_event(self):
        published = []

        def _capture(payload):
            published.append(payload)

        with mock.patch(
            "apps.schoolops.substitute_handover.find_substitute_candidates",
            return_value=[],
        ):
            shift = open_shift(
                school=self.school,
                absent_teacher_id=99,
                work_date=date.today(),
                publish_fn=_capture,
            )
        self.assertTrue(shift.shift_id)
        self.assertEqual(published[0]["event"], "shift.open")
        self.assertEqual(published[0]["schema_version"], "substitute_shift.v1")

    def test_second_open_raises(self):
        d = date.today()
        with mock.patch(
            "apps.schoolops.substitute_handover.find_substitute_candidates",
            return_value=[],
        ):
            open_shift(school=self.school, absent_teacher_id=1, work_date=d, period_label="P1")
            with self.assertRaises(ShiftAlreadyBooked):
                open_shift(school=self.school, absent_teacher_id=2, work_date=d, period_label="P1")


class MigrationIntakeBootstrapTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Migrate School",
            slug="migrate-school",
            subdomain="migrate-school",
            country_code="CM",
            is_active=True,
        )

    def test_bootstrap_creates_bundle(self):
        from apps.migration_cloud.models import MigrationBundle
        from apps.migration_cloud.services.intake_init import bootstrap_migration_bundle

        with mock.patch(
            "apps.migration_cloud.services.intake_init._enqueue_advance",
        ):
            bundle_id = bootstrap_migration_bundle(
                school=self.school,
                source="powerschool",
                actor_id=1,
            )
        self.assertIsNotNone(bundle_id)
        bundle = MigrationBundle.objects.get(pk=bundle_id)
        self.assertEqual(bundle.school_id, self.school.pk)
        self.assertIn("PowerSchool", bundle.source_hint)


class ConcurrentSubstituteLockSmokeTests(TestCase):
    """Lightweight concurrency smoke — full 50k load uses OSS Locust/k6 externally."""

    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Concurrent School",
            slug="concurrent-school",
            subdomain="concurrent-school",
            country_code="CM",
            is_active=True,
        )

    def test_parallel_lock_contention(self):
        import threading
        from datetime import date

        work_date = date(2026, 6, 17)
        wins = {"count": 0}
        barrier = threading.Barrier(32)

        def worker():
            barrier.wait()
            if acquire_shift_slot_lock(
                school_id=self.school.pk,
                work_date=work_date,
                period_label="P1",
            ):
                wins["count"] += 1
                release_shift_slot_lock(
                    school_id=self.school.pk,
                    work_date=work_date,
                    period_label="P1",
                )

        threads = [threading.Thread(target=worker) for _ in range(32)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertGreaterEqual(wins["count"], 1)
        self.assertLessEqual(wins["count"], 32)
