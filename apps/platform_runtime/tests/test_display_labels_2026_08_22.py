"""An internal token must never reach a person as a slug.

Regression cover for the Tenant 360 banner that read

    Exact next confirmations: funding_type, learner_scale, connectivity,
    operating_model

and for the two siblings the same audit turned up: the confidence breakdown
rendering "Inputcompleteness", and the tenant lifecycle strip rendering
"dailyoperations" on every page of a live school.

DB-free by design (``SimpleTestCase``) so it runs in the deps-free lanes.
"""

from __future__ import annotations

from django.test import SimpleTestCase
from django.utils import translation

from apps.platform_runtime.display_labels import (
    ACRONYMS,
    humanize_all,
    humanize_token,
    label_for,
    labels_for,
)
from apps.platform_runtime.tenant_operational_lifecycle import (
    ALL_OPERATIONAL_STATES,
    OPERATIONAL_STATE_LABELS,
    STATE_DAILY_OPERATIONS,
    operational_state_label,
)


class HumanizeTokenTests(SimpleTestCase):
    def test_snake_case_becomes_sentence_case(self):
        self.assertEqual(humanize_token("daily_operations"), "Daily operations")
        self.assertEqual(
            humanize_token("input_completeness"), "Input completeness"
        )
        self.assertEqual(
            humanize_token("academic_year_close"), "Academic year close"
        )

    def test_kebab_case_is_handled_too(self):
        self.assertEqual(humanize_token("soft-glass"), "Soft glass")
        self.assertEqual(
            humanize_token("needs-confirmation"), "Needs confirmation"
        )

    def test_acronyms_are_uppercased_anywhere_in_the_token(self):
        self.assertEqual(humanize_token("sms_verify"), "SMS verify")
        self.assertEqual(humanize_token("gateway_api"), "Gateway API")
        self.assertEqual(humanize_token("api"), "API")

    def test_deliberate_internal_capitals_survive(self):
        # A proper noun somebody typed, not a slug to be re-cased.
        self.assertEqual(humanize_token("PowerSchool"), "PowerSchool")
        self.assertEqual(humanize_token("vendor_PowerSchool"), "Vendor PowerSchool")

    def test_single_lowercase_word_is_capitalised(self):
        self.assertEqual(humanize_token("connectivity"), "Connectivity")

    def test_humanize_never_returns_a_separator(self):
        # The whole point: whatever comes out is readable as words.
        for token in (
            "a_b",
            "a-b",
            "read_only",
            "purge_scheduled",
            "recommendation-readiness-not-prediction-probability",
        ):
            with self.subTest(token=token):
                result = humanize_token(token)
                self.assertNotIn("_", result)
                self.assertNotIn("-", result)

    def test_unusable_input_returns_empty_string_not_a_crash(self):
        for value in (None, 123, [], {}, "", "   ", "__", b"bytes"):
            with self.subTest(value=value):
                self.assertEqual(humanize_token(value), "")

    def test_cut_filter_behaviour_is_what_this_replaces(self):
        # Pinning the defect so the rationale cannot be lost: `cut` deletes the
        # separator. This is what shipped on three surfaces.
        self.assertEqual("daily_operations".replace("_", ""), "dailyoperations")
        self.assertNotEqual(
            humanize_token("daily_operations"), "dailyoperations"
        )


class HumanizeCollectionTests(SimpleTestCase):
    def test_humanize_all_maps_and_drops_blanks(self):
        self.assertEqual(
            humanize_all(["funding_type", "", None, "learner_scale"]),
            ["Funding type", "Learner scale"],
        )

    def test_a_bare_string_is_not_treated_as_an_iterable_of_characters(self):
        self.assertEqual(humanize_all("funding_type"), [])

    def test_non_iterable_returns_empty(self):
        self.assertEqual(humanize_all(None), [])
        self.assertEqual(humanize_all(7), [])


class LabelForTests(SimpleTestCase):
    REGISTRY = {"known": "A curated sentence"}

    def test_curated_label_wins(self):
        self.assertEqual(label_for(self.REGISTRY, "known"), "A curated sentence")

    def test_unregistered_token_is_humanized_not_dropped(self):
        # A strange label is recoverable; a blank one is not. report_library.html
        # shipped an empty <caption> because the fallback was nothing at all.
        self.assertEqual(label_for(self.REGISTRY, "some_key"), "Some key")

    def test_empty_token_returns_the_default(self):
        self.assertEqual(label_for(self.REGISTRY, "", default="—"), "—")
        self.assertEqual(label_for(self.REGISTRY, None, default="—"), "—")

    def test_labels_for_preserves_order(self):
        self.assertEqual(
            labels_for(self.REGISTRY, ["some_key", "known"]),
            ["Some key", "A curated sentence"],
        )


class OperationalStateLabelTests(SimpleTestCase):
    def test_every_declared_state_has_a_curated_label(self):
        missing = [
            state
            for state in ALL_OPERATIONAL_STATES
            if state not in OPERATIONAL_STATE_LABELS
        ]
        self.assertEqual(
            missing, [], f"lifecycle states with no label: {missing}"
        )

    def test_no_label_outlives_its_state(self):
        orphans = sorted(
            set(OPERATIONAL_STATE_LABELS) - set(ALL_OPERATIONAL_STATES)
        )
        self.assertEqual(orphans, [], f"stale lifecycle labels: {orphans}")

    def test_no_label_is_just_the_slug(self):
        for state, label in OPERATIONAL_STATE_LABELS.items():
            with self.subTest(state=state):
                self.assertNotIn("_", str(label))
                # A one-word state like `offboarding` legitimately labels as
                # "Offboarding"; what is banned is shipping the slug verbatim.
                self.assertNotEqual(str(label), state)
                self.assertTrue(str(label)[:1].isupper(), str(label))

    def test_the_shipped_defect_is_gone(self):
        self.assertEqual(
            operational_state_label(STATE_DAILY_OPERATIONS),
            "Day-to-day operations",
        )
        self.assertNotEqual(
            operational_state_label(STATE_DAILY_OPERATIONS), "dailyoperations"
        )

    def test_an_unknown_state_is_humanized_rather_than_blank(self):
        self.assertEqual(
            operational_state_label("some_future_state"), "Some future state"
        )

    def test_an_empty_state_is_empty(self):
        # The strip template already guards on falsy state; do not invent a chip.
        self.assertEqual(operational_state_label(""), "")
        self.assertEqual(operational_state_label(None), "")

    def test_labels_are_lazy_so_they_translate_per_request(self):
        # A str() at import time freezes the label to the language that happened
        # to be active when the module loaded.
        for label in OPERATIONAL_STATE_LABELS.values():
            with self.subTest(label=label):
                self.assertNotIsInstance(label, str)

    def test_label_resolution_returns_a_real_string(self):
        with translation.override("en"):
            self.assertIsInstance(
                operational_state_label(STATE_DAILY_OPERATIONS), str
            )


class AcronymParityTests(SimpleTestCase):
    def test_the_two_humanizers_agree_about_acronyms(self):
        # setup_studio.wizard_labels title-cases wizard STEP headings; this
        # module sentence-cases VALUES. Different casing is deliberate, but two
        # humanizers disagreeing about whether "sms" is "SMS" is not.
        from apps.setup_studio.wizard_labels import _ACRONYMS

        self.assertEqual(set(_ACRONYMS), set(ACRONYMS))
