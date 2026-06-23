"""Wave 1 — local-first currency SoT.

Guards that tenant money is the SCHOOL's currency, never a hardcoded literal:

  1. ``School.resolve_currency`` cascade (explicit override → region → country pack →
     platform default), never blank, always upper-cased;
  2. the ``_apply_local_currency_default`` pre_save filler only acts on inserts with a
     blank currency and never overrides an explicit value;
  3. ``_default_currency_symbol`` returns a SYMBOL, not the 3-letter code (bug fix);
  4. both Wave-1 migrations exist;
  5. (DB) a newly-created advancement row inherits its school's resolved currency.
"""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase

_ROOT = Path(__file__).resolve().parents[3]


class ResolveCurrencyCascadeTests(SimpleTestCase):
    def _school(self, **kw):
        from apps.schools.models import School

        return School(**kw)

    def test_explicit_override_wins_and_uppercases(self):
        self.assertEqual(self._school(currency="gbp").resolve_currency(), "GBP")

    def test_blank_no_country_falls_back_to_platform_default(self):
        # No country_code → the cascade never touches the country pack (DB-free path).
        expected = getattr(settings, "PLATFORM_DEFAULT_CURRENCY", "USD").upper()
        self.assertEqual(self._school().resolve_currency(), expected)


class ApplyLocalCurrencyDefaultTests(SimpleTestCase):
    class _State:
        def __init__(self, adding):
            self.adding = adding

    class _FakeSchool:
        def resolve_currency(self):
            return "NGN"

    class _FakeRow:
        def __init__(self, adding=True, currency="", school=None):
            self._state = ApplyLocalCurrencyDefaultTests._State(adding)
            self.currency = currency
            self.school = school

    def _apply(self, row):
        from apps.schools.models import _apply_local_currency_default

        _apply_local_currency_default(row)
        return row

    def test_fills_blank_from_school_on_insert(self):
        row = self._FakeRow(adding=True, currency="", school=self._FakeSchool())
        self.assertEqual(self._apply(row).currency, "NGN")

    def test_does_not_override_explicit_currency(self):
        row = self._FakeRow(adding=True, currency="EUR", school=self._FakeSchool())
        self.assertEqual(self._apply(row).currency, "EUR")

    def test_noop_on_update(self):
        row = self._FakeRow(adding=False, currency="", school=self._FakeSchool())
        self.assertEqual(self._apply(row).currency, "")

    def test_falls_back_to_platform_default_without_school(self):
        from apps.schools.models import _default_currency

        row = self._FakeRow(adding=True, currency="", school=None)
        self.assertEqual(self._apply(row).currency, _default_currency())


class CurrencySymbolDefaultTests(SimpleTestCase):
    def test_default_symbol_is_symbol_not_code(self):
        from apps.finance.models import _default_currency, _default_currency_symbol

        symbol = _default_currency_symbol()
        self.assertTrue(symbol)
        # For the common USD platform default the symbol must not be the literal code.
        if _default_currency() == "USD":
            self.assertEqual(symbol, "$")


class MigrationPresenceTests(SimpleTestCase):
    def test_wave1_migrations_exist(self):
        self.assertTrue(
            (
                _ROOT
                / "apps/schools/migrations/0073_school_currency_alter_advancementgift_currency_and_more.py"
            ).exists()
        )
        self.assertTrue(
            (
                _ROOT
                / "apps/finance/migrations/0073_alter_complianceprofile_currency_symbol.py"
            ).exists()
        )


class LocalFirstCurrencyDBTests(TestCase):
    def _school(self, **kw):
        import uuid

        from apps.schools.models import School

        tag = uuid.uuid4().hex[:10]
        return School.objects.create(
            name="LF " + tag,
            slug=f"lf-{tag}",
            subdomain=f"lf-{tag}",
            **kw,
        )

    def test_school_resolves_country_currency(self):
        school = self._school(country_code="NG")
        self.assertEqual(school.resolve_currency(), "NGN")

    def test_resolve_currency_never_blank_for_unknown_country(self):
        school = self._school(country_code="ZZ")
        self.assertTrue(school.resolve_currency())

    def test_new_campaign_inherits_school_currency(self):
        from apps.schools.models import FundraisingCampaign

        school = self._school(country_code="NG")
        camp = FundraisingCampaign.objects.create(school=school, name="Annual Fund")
        self.assertEqual(camp.currency, "NGN")

    def test_explicit_campaign_currency_preserved(self):
        from apps.schools.models import FundraisingCampaign

        school = self._school(country_code="NG")
        camp = FundraisingCampaign.objects.create(
            school=school, name="USD Appeal", currency="USD"
        )
        self.assertEqual(camp.currency, "USD")
