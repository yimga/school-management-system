"""10X studio seeding — per-school GradingScale auto-provisioned from the country.

Before this, the country pack computed a grading scale into school.settings but no
GradingScale model row was created at provision, so a new school showed "no grading scale
configured" until an admin manually ran the wizard. ensure_local_grading_scale closes the
gap: country preset → scale type → per-school default GradingScale + matching default
AssessmentWeights, idempotent, never overriding an admin/wizard choice.
"""

from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase


class ScaleConfigTests(SimpleTestCase):
    def test_preset_map_values_are_valid_scale_types(self):
        from apps.evals.grading_provisioning import (
            _PRESET_TO_SCALE_TYPE,
            _VALID_SCALE_TYPES,
        )

        for preset, scale in _PRESET_TO_SCALE_TYPE.items():
            self.assertIn(scale, _VALID_SCALE_TYPES, preset)

    def test_key_presets_map_as_expected(self):
        """Francophone schools now get their OWN scale type, not the generic 0–20.

        ``francophone_bac`` used to map to ``numeric_0_20``; the platform since
        grew a dedicated ``french_0_20`` (plus us_letter / uk_gcse_9_1 / waec_letter
        and the rest), so each country's report card can carry its real band
        labels instead of a borrowed A–E. What must NOT drift is the axis: a
        Cameroon or France school is still marked out of 20, and
        ``test_francophone_preset_is_still_a_20_point_axis`` pins that.
        """
        from apps.evals.grading_provisioning import _PRESET_TO_SCALE_TYPE

        self.assertEqual(_PRESET_TO_SCALE_TYPE["francophone_bac"], "french_0_20")
        self.assertEqual(_PRESET_TO_SCALE_TYPE["american"], "us_letter")
        self.assertEqual(_PRESET_TO_SCALE_TYPE["british_igcse"], "uk_gcse_9_1")
        self.assertEqual(_PRESET_TO_SCALE_TYPE["west_african_waec"], "waec_letter")

    def test_francophone_preset_is_still_a_20_point_axis(self):
        """The invariant behind the rename: Cameroon/France are marked out of 20.

        A Buea school accepting a mark of 25 was a real defect; the axis is the
        thing that matters, not the name of the scale.
        """
        from apps.evals.grading import ASSESSMENT_WEIGHTS_SCALE_MAP
        from apps.evals.grading_provisioning import _PRESET_TO_SCALE_TYPE, _scale_config

        scale_type = _PRESET_TO_SCALE_TYPE["francophone_bac"]
        self.assertEqual(ASSESSMENT_WEIGHTS_SCALE_MAP[scale_type], "0-20")
        self.assertEqual(_scale_config(scale_type)["score_scale"], 20)

    def test_scale_config_percentage(self):
        from apps.evals.grading_provisioning import _scale_config

        cfg = _scale_config("percentage")
        self.assertEqual(cfg["score_scale"], 100)
        self.assertEqual(cfg["pass_threshold"], 50.0)
        self.assertEqual(cfg["grade_thresholds"]["A"], 80.0)

    def test_scale_config_numeric_0_20(self):
        from apps.evals.grading_provisioning import _scale_config

        cfg = _scale_config("numeric_0_20")
        self.assertEqual(cfg["score_scale"], 20)
        self.assertEqual(cfg["pass_threshold"], 10.0)


class ResolveLocalScaleTypeTests(SimpleTestCase):
    """Precedence: explicit per-school choice > country derivation > platform
    default hint > neutral. The key local-first guarantee is that a platform-wide
    ``default_grading_scale`` no longer overrides per-tenant country derivation.

    Uses ``country_code='FR'`` (in the curated francophone override) so
    ``resolve_grading_preset_key`` short-circuits without any DB access.
    """

    def _school(self, settings=None, country_code="FR"):
        return SimpleNamespace(settings=settings, country_code=country_code)

    def test_normalize_scale_type_maps_wizard_keys_and_dashes(self):
        from apps.evals.grading_provisioning import _normalize_scale_type

        self.assertEqual(_normalize_scale_type("gpa_4"), "gpa_4_0")
        self.assertEqual(_normalize_scale_type("letter"), "letter_a_e")
        self.assertEqual(_normalize_scale_type("numeric-0-20"), "numeric_0_20")
        self.assertEqual(_normalize_scale_type(""), "")
        self.assertEqual(_normalize_scale_type(None), "")

    def test_school_explicit_reads_nested_then_top_level(self):
        from apps.evals.grading_provisioning import _school_explicit_scale_type

        self.assertEqual(
            _school_explicit_scale_type(
                self._school({"runtime_defaults": {"default_grading_scale": "gpa_4"}})
            ),
            "gpa_4_0",
        )
        self.assertEqual(
            _school_explicit_scale_type(self._school({"default_grading_scale": "letter"})),
            "letter_a_e",
        )
        # Nested wins over top-level (mirrors the effective-settings merge order).
        self.assertEqual(
            _school_explicit_scale_type(
                self._school(
                    {
                        "default_grading_scale": "letter",
                        "runtime_defaults": {"default_grading_scale": "gpa_4"},
                    }
                )
            ),
            "gpa_4_0",
        )
        self.assertEqual(_school_explicit_scale_type(self._school({})), "")
        self.assertEqual(_school_explicit_scale_type(self._school(None)), "")

    def test_explicit_per_school_choice_wins_over_country(self):
        from apps.evals.grading_provisioning import resolve_local_scale_type

        # Admin picked GPA for this FR school; the pick wins over FR -> numeric_0_20.
        school = self._school({"runtime_defaults": {"default_grading_scale": "gpa_4"}})
        self.assertEqual(resolve_local_scale_type(school), "gpa_4_0")

    def test_country_derivation_when_no_explicit_choice(self):
        from apps.evals.grading_provisioning import resolve_local_scale_type

        # Blank settings -> country wins. Because step 2 returns here, a
        # platform-wide default (step 3) can never override the country.
        # FR derives the dedicated French scale (still a 0–20 axis).
        self.assertEqual(resolve_local_scale_type(self._school({})), "french_0_20")
        self.assertEqual(resolve_local_scale_type(self._school(None)), "french_0_20")

    def test_school_explicit_ignores_non_dict_settings(self):
        from apps.evals.grading_provisioning import _school_explicit_scale_type

        self.assertEqual(_school_explicit_scale_type(self._school("oops")), "")
        self.assertEqual(_school_explicit_scale_type(self._school(123)), "")
        self.assertEqual(
            _school_explicit_scale_type(self._school({"runtime_defaults": "notadict"})), ""
        )

    def test_platform_hint_used_only_when_no_country(self):
        import apps.evals.grading_provisioning as gp

        original = gp._scale_type_from_cascade
        try:
            # Country-less school + a platform default -> the platform hint applies.
            gp._scale_type_from_cascade = lambda school: "gpa_4_0"
            self.assertEqual(gp.resolve_local_scale_type(self._school({}, country_code="")), "gpa_4_0")
            # No country AND no platform default -> neutral percentage.
            gp._scale_type_from_cascade = lambda school: ""
            self.assertEqual(gp.resolve_local_scale_type(self._school({}, country_code="")), "percentage")
            # A known country still beats the platform hint.
            gp._scale_type_from_cascade = lambda school: "gpa_4_0"
            self.assertEqual(gp.resolve_local_scale_type(self._school({}, country_code="FR")), "french_0_20")
        finally:
            gp._scale_type_from_cascade = original

    def test_resolve_school_score_scale_fallback_path(self):
        # A pk-less stub skips the AssessmentWeights read and falls back to the
        # country-derived band score_scale — francophone -> 20, never the locale 100.
        from decimal import Decimal

        from apps.evals.grading_provisioning import resolve_school_score_scale

        self.assertEqual(resolve_school_score_scale(self._school({}, country_code="FR")), Decimal("20"))
        self.assertEqual(resolve_school_score_scale(None), Decimal("100"))

    def test_scale_config_gpa_and_letter(self):
        from apps.evals.grading_provisioning import _scale_config

        gpa = _scale_config("gpa_4_0")
        self.assertEqual(gpa["score_scale"], 4)
        self.assertGreater(gpa["pass_threshold"], 0)
        letter = _scale_config("letter_a_e")
        self.assertIn("grade_thresholds", letter)
        self.assertEqual(set(letter["grade_thresholds"]), {"A", "B", "C", "D", "E"})


class GradingProvisioningDBTests(TestCase):
    def _school(self, **kw):
        import uuid

        from apps.schools.models import School

        tag = uuid.uuid4().hex[:10]
        return School.objects.create(
            name="GP " + tag, slug=f"gp-{tag}", subdomain=f"gp-{tag}", **kw
        )

    def test_seeds_country_scale_and_default_weights(self):
        from apps.academics.models import AcademicYear
        from apps.evals.grading_provisioning import ensure_local_grading_scale
        from apps.evals.models import AssessmentWeights, GradingScale

        school = self._school(country_code="FR")  # francophone_bac → french_0_20
        ay = AcademicYear.objects.create(
            school=school, name="2025/2026", start_date="2025-09-01", end_date="2026-07-31"
        )
        res = ensure_local_grading_scale(school, academic_year=ay)
        self.assertTrue(res["ok"])
        scale = GradingScale.objects.get(school=school, is_default=True)
        self.assertEqual(scale.scale_type, "french_0_20")
        self.assertTrue(
            AssessmentWeights.objects.filter(
                school=school, academic_year=ay, term=None, classroom=None
            ).exists()
        )

    def test_idempotent_second_call_skips(self):
        from apps.evals.grading_provisioning import ensure_local_grading_scale
        from apps.evals.models import GradingScale

        school = self._school(country_code="US")
        ensure_local_grading_scale(school)
        res2 = ensure_local_grading_scale(school)
        self.assertEqual(res2.get("skipped"), "default_scale_exists")
        self.assertEqual(GradingScale.objects.filter(school=school, is_default=True).count(), 1)

    def test_respects_existing_admin_default(self):
        from apps.evals.grading_provisioning import ensure_local_grading_scale
        from apps.evals.models import GradingScale

        school = self._school(country_code="FR")
        GradingScale.objects.create(
            school=school, code="wizard-default", name="Admin pick",
            scale_type="percentage", is_default=True, is_active=True,
        )
        res = ensure_local_grading_scale(school)
        self.assertEqual(res.get("skipped"), "default_scale_exists")
        # Admin's percentage choice preserved, not overridden by FR→numeric_0_20.
        self.assertEqual(
            GradingScale.objects.get(school=school, is_default=True).scale_type, "percentage"
        )

    def test_aligns_locale_grading_scale_with_operational(self):
        # The locale/display grading_scale converges with the operational scale so
        # reports match computation. FR's generic 0-100 profile default is corrected
        # to 0-20 (the scale grades are actually computed on).
        from apps.evals.grading_provisioning import ensure_local_grading_scale
        from apps.siteconfig.tenant_config import get_tenant_locale

        school = self._school(country_code="FR")
        school.settings = {"grading_scale": "0-100"}  # simulate generic profile default
        school.save(update_fields=["settings"])
        res = ensure_local_grading_scale(school)
        self.assertTrue(res.get("locale_scale_aligned"))
        school.refresh_from_db()
        self.assertEqual((school.settings or {}).get("grading_scale"), "0-20")
        self.assertEqual(get_tenant_locale(school=school).get("grading_scale"), "0-20")

    def test_admin_default_leaves_locale_settings_untouched(self):
        from apps.evals.grading_provisioning import ensure_local_grading_scale
        from apps.evals.models import GradingScale

        school = self._school(country_code="FR")
        school.settings = {"grading_scale": "0-100"}
        school.save(update_fields=["settings"])
        GradingScale.objects.create(
            school=school, code="wizard-default", name="Admin pick",
            scale_type="percentage", is_default=True, is_active=True,
        )
        ensure_local_grading_scale(school)
        school.refresh_from_db()
        # Skip path returns before locale alignment — admin's settings untouched.
        self.assertEqual((school.settings or {}).get("grading_scale"), "0-100")
