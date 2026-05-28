"""v4.00.14 — curriculum map invariants."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.academics.curriculum_map import (
    chain_for_subject,
    list_supported_subjects,
    resolve_topic_siblings,
)


class CurriculumMapTests(SimpleTestCase):
    def test_subjects_are_listed(self) -> None:
        subjects = list_supported_subjects()
        self.assertIn("math", subjects)
        self.assertIn("english", subjects)
        self.assertIn("physics", subjects)

    def test_chain_for_known_subject_is_nonempty(self) -> None:
        chain = chain_for_subject("math")
        self.assertGreater(len(chain), 2)
        self.assertEqual(chain[0], "math.arithmetic")

    def test_chain_for_unknown_subject_is_empty(self) -> None:
        self.assertEqual(chain_for_subject("does-not-exist"), ())

    def test_siblings_for_middle_topic_returns_three_distinct(self) -> None:
        siblings = resolve_topic_siblings(
            subject_key="math",
            current_topic_key="math.algebra_intro",
        )
        # algebra_intro is index 2 of the math chain.
        self.assertEqual(siblings["remedial"], "math.fractions")
        self.assertEqual(siblings["follow_on"], "math.linear_equations")
        self.assertEqual(siblings["advanced"], "math.quadratic_equations")

    def test_siblings_for_first_topic_clamps_remedial(self) -> None:
        siblings = resolve_topic_siblings(
            subject_key="math",
            current_topic_key="math.arithmetic",
        )
        # remedial cannot go below index 0.
        self.assertEqual(siblings["remedial"], "math.arithmetic")
        self.assertEqual(siblings["follow_on"], "math.fractions")

    def test_siblings_for_last_topic_clamps_advanced(self) -> None:
        chain = chain_for_subject("math")
        last_topic = chain[-1]
        siblings = resolve_topic_siblings(
            subject_key="math",
            current_topic_key=last_topic,
        )
        self.assertEqual(siblings["follow_on"], last_topic)
        self.assertEqual(siblings["advanced"], last_topic)

    def test_unknown_subject_returns_all_none(self) -> None:
        siblings = resolve_topic_siblings(
            subject_key="basket_weaving",
            current_topic_key="basket_weaving.intro",
        )
        self.assertIsNone(siblings["remedial"])
        self.assertIsNone(siblings["follow_on"])
        self.assertIsNone(siblings["advanced"])

    def test_school_override_wins_over_default(self) -> None:
        override_chain = [
            "math.first",
            "math.second",
            "math.third",
            "math.fourth",
        ]
        siblings = resolve_topic_siblings(
            subject_key="math",
            current_topic_key="math.second",
            school_settings={
                "academics": {
                    "curriculum_map": {"math": override_chain},
                },
            },
        )
        self.assertEqual(siblings["remedial"], "math.first")
        self.assertEqual(siblings["follow_on"], "math.third")
        self.assertEqual(siblings["advanced"], "math.fourth")

    def test_normalization_accepts_prefixed_subject(self) -> None:
        # `english.essay_structure` should resolve to the `english` chain.
        siblings = resolve_topic_siblings(
            subject_key="english.essay_structure",
            current_topic_key="english.essay_structure",
        )
        self.assertIsNotNone(siblings["follow_on"])
