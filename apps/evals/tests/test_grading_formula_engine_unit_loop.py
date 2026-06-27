"""Unit tests for the pure safe-eval grading formula engine.

No DB access: ``apps.evals.grading_formula_engine`` is a self-contained
AST evaluator (no Django models). The existing ``test_grading_formula_live_path``
suite is DB-backed and only proves the engine is *wired into* the live
Evaluation save path; it never exercises the evaluator's own arithmetic,
the allowed-function whitelist, the error contract, or the security
rejection of disallowed syntax. These assertions lock that pure behavior.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.evals.grading_formula_engine import (
    PRESET_GRADING_FORMULAS,
    GradingFormulaError,
    GradingFormulaResult,
    evaluate_grading_formula,
)


def _val(formula_text: str, **variables: float) -> float:
    return evaluate_grading_formula(
        formula_text=formula_text, variables=variables
    ).value


class GradingFormulaArithmeticTests(SimpleTestCase):
    def test_basic_operators(self):
        self.assertEqual(_val("2 + 3"), 5.0)
        self.assertEqual(_val("10 - 4"), 6.0)
        self.assertEqual(_val("3 * 4"), 12.0)
        self.assertEqual(_val("10 / 4"), 2.5)
        self.assertEqual(_val("10 % 3"), 1.0)
        self.assertEqual(_val("2 ** 3"), 8.0)

    def test_unary_minus_and_plus(self):
        self.assertEqual(_val("-5"), -5.0)
        self.assertEqual(_val("+7"), 7.0)

    def test_variables_are_substituted(self):
        self.assertEqual(_val("exam * 0.6 + coursework * 0.4", exam=15, coursework=20), 17.0)

    def test_allowed_functions(self):
        self.assertEqual(_val("min(20, 25)"), 20.0)
        self.assertEqual(_val("max(0, -3)"), 0.0)
        self.assertEqual(_val("abs(-9)"), 9.0)
        self.assertEqual(_val("round(2.345, 1)"), 2.3)
        self.assertEqual(_val("sqrt(16)"), 4.0)
        self.assertEqual(_val("floor(3.9)"), 3.0)
        self.assertEqual(_val("ceil(3.1)"), 4.0)
        self.assertEqual(_val("pow(2, 4)"), 16.0)

    def test_result_carries_scale_key_and_normalized_text(self):
        result = evaluate_grading_formula(
            formula_text="  1 + 1 ", variables={}, scale_key="custom-x"
        )
        self.assertIsInstance(result, GradingFormulaResult)
        self.assertEqual(result.value, 2.0)
        self.assertEqual(result.scale_key, "custom-x")
        self.assertEqual(result.formula_text, "1 + 1")


class GradingFormulaErrorContractTests(SimpleTestCase):
    def test_empty_formula_raises(self):
        with self.assertRaises(GradingFormulaError):
            evaluate_grading_formula(formula_text="", variables={})
        with self.assertRaises(GradingFormulaError):
            evaluate_grading_formula(formula_text="   ", variables={})

    def test_formula_too_long_raises(self):
        with self.assertRaises(GradingFormulaError):
            evaluate_grading_formula(formula_text="1+" * 300 + "1", variables={})

    def test_division_by_zero_raises_grading_error(self):
        with self.assertRaises(GradingFormulaError):
            evaluate_grading_formula(formula_text="1 / 0", variables={})

    def test_unknown_variable_raises(self):
        with self.assertRaises(GradingFormulaError):
            evaluate_grading_formula(formula_text="missing + 1", variables={})

    def test_invalid_variable_name_raises(self):
        with self.assertRaises(GradingFormulaError):
            evaluate_grading_formula(formula_text="1 + 1", variables={"bad name": 1.0})

    def test_syntax_error_raises_grading_error(self):
        with self.assertRaises(GradingFormulaError):
            evaluate_grading_formula(formula_text="1 +", variables={})


class GradingFormulaSecurityTests(SimpleTestCase):
    def test_disallowed_function_call_rejected(self):
        with self.assertRaises(GradingFormulaError):
            evaluate_grading_formula(formula_text="open('x')", variables={})

    def test_attribute_access_rejected(self):
        with self.assertRaises(GradingFormulaError):
            evaluate_grading_formula(
                formula_text="x.__class__", variables={"x": 1.0}
            )

    def test_subscript_and_comparison_rejected(self):
        # Subscript is an unsupported node type.
        with self.assertRaises(GradingFormulaError):
            evaluate_grading_formula(formula_text="x[0]", variables={"x": 1.0})
        # Comparison operators are not in the allowed binop set.
        with self.assertRaises(GradingFormulaError):
            evaluate_grading_formula(formula_text="1 < 2", variables={})


class GradingFormulaPresetTests(SimpleTestCase):
    def test_presets_are_all_evaluable(self):
        # Each shipped preset must parse + evaluate with sane sample inputs.
        sample = {"exam": 15.0, "coursework": 12.0}
        for key, formula in PRESET_GRADING_FORMULAS.items():
            result = evaluate_grading_formula(formula_text=formula, variables=sample)
            self.assertIsInstance(result.value, float, key)

    def test_francophone_preset_clamps_to_0_20_band(self):
        # min(20, max(0, ...)) guarantees the result never escapes [0, 20].
        formula = PRESET_GRADING_FORMULAS["francophone_0_20"]
        high = _val(formula, exam=100.0, coursework=100.0)
        low = _val(formula, exam=-50.0, coursework=-50.0)
        self.assertLessEqual(high, 20.0)
        self.assertGreaterEqual(low, 0.0)

    def test_us_gpa_preset_clamps_to_4_point_scale(self):
        formula = PRESET_GRADING_FORMULAS["us_gpa_4"]
        self.assertEqual(_val(formula, exam=100.0), 4.0)
        self.assertEqual(_val(formula, exam=0.0), 0.0)
