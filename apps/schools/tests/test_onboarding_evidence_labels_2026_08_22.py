"""The confidence envelope must be able to say what it wants confirmed.

Tenant 360 rendered "Exact next confirmations: funding_type, learner_scale,
connectivity, operating_model" -- the dict keys, under a banner promising
exactness -- while twenty lines away in the same function ``missing_inputs``
said "funding model" and "expected learners" because somebody had written
those words by hand. Only one of the two lists reached a screen.

DB-free (``SimpleTestCase``).
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.schools.onboarding_recommendations import (
    CRITICAL_EVIDENCE_KEYS,
    CRITICAL_EVIDENCE_LABELS,
    _build_confidence_envelope,
    build_onboarding_recommendations,
    hydrate_confidence_display,
)

from apps.siteconfig.tests._template_nodes import (
    assert_wires,
)

_TN_ROOT = Path(__file__).resolve().parents[3]


def _empty_envelope() -> dict:
    """An envelope with nothing supplied, so every evidence key is missing."""
    return _build_confidence_envelope(
        country="",
        cycles=[],
        languages=[],
        profile={},
        explicit_inputs=set(),
        warnings=[],
        blueprint={},
    )


class EvidenceVocabularyTests(SimpleTestCase):
    def test_every_key_the_engine_emits_is_declared(self):
        envelope = _empty_envelope()
        self.assertEqual(
            set(envelope["critical_evidence"]),
            set(CRITICAL_EVIDENCE_KEYS),
            "the inline `critical` dict and CRITICAL_EVIDENCE_KEYS drifted",
        )

    def test_every_declared_key_has_a_label(self):
        missing = [k for k in CRITICAL_EVIDENCE_KEYS if k not in CRITICAL_EVIDENCE_LABELS]
        self.assertEqual(missing, [], f"unlabelled evidence keys: {missing}")

    def test_no_label_outlives_its_key(self):
        orphans = sorted(set(CRITICAL_EVIDENCE_LABELS) - set(CRITICAL_EVIDENCE_KEYS))
        self.assertEqual(orphans, [], f"stale evidence labels: {orphans}")

    def test_no_label_is_just_the_key_in_disguise(self):
        for key, label in CRITICAL_EVIDENCE_LABELS.items():
            with self.subTest(key=key):
                text = str(label)
                self.assertNotIn("_", text)
                # `country` -> "Country" is a real label; the slug verbatim is not.
                self.assertNotEqual(text, key)
                self.assertTrue(text[:1].isupper(), text)

    def test_labels_are_lazy_so_they_translate_per_request(self):
        for label in CRITICAL_EVIDENCE_LABELS.values():
            with self.subTest(label=label):
                self.assertNotIsInstance(label, str)


class EnvelopeContractTests(SimpleTestCase):
    def test_the_stored_envelope_stays_machine_only(self):
        # Display text must NOT be persisted: `ensure_school_recommendations`
        # returns a matching stored manifest untouched, so a label frozen in it
        # would keep whatever language built it, forever.
        envelope = _empty_envelope()
        for field in (
            "missing_critical_evidence_labels",
            "label_display",
            "status_display",
            "registry_status_display",
        ):
            self.assertNotIn(field, envelope)

    def test_machine_keys_are_unchanged(self):
        envelope = _empty_envelope()
        self.assertEqual(
            envelope["missing_critical_evidence"], list(CRITICAL_EVIDENCE_KEYS)
        )
        self.assertEqual(envelope["registry_status"], "incomplete")
        self.assertEqual(envelope["label"], "low")


class HydrationTests(SimpleTestCase):
    def test_hydration_adds_words_for_every_missing_key(self):
        hydrated = hydrate_confidence_display(_empty_envelope())
        labels = hydrated["missing_critical_evidence_labels"]
        self.assertEqual(len(labels), len(CRITICAL_EVIDENCE_KEYS))
        self.assertIn("How the school is funded", labels)
        self.assertIn("Internet reliability on site", labels)

    def test_the_reported_banner_no_longer_contains_a_slug(self):
        hydrated = hydrate_confidence_display(_empty_envelope())
        rendered = "; ".join(hydrated["missing_critical_evidence_labels"])
        for slug in (
            "funding_type",
            "learner_scale",
            "connectivity",
            "operating_model",
        ):
            self.assertNotIn(slug, rendered)

    def test_status_and_registry_are_humanized(self):
        hydrated = hydrate_confidence_display(_empty_envelope())
        self.assertEqual(hydrated["label_display"], "Low")
        self.assertEqual(hydrated["status_display"], "Insufficient evidence")
        self.assertEqual(hydrated["registry_status_display"], "Incomplete")

    def test_hydration_never_mutates_the_stored_envelope(self):
        envelope = _empty_envelope()
        before = dict(envelope)
        hydrate_confidence_display(envelope)
        self.assertEqual(envelope, before)

    def test_a_manifest_stored_before_this_existed_still_renders(self):
        # The whole reason hydration happens at READ time.
        legacy = {
            "label": "provisional",
            "status": "needs-confirmation",
            "registry_status": "resolved",
            "missing_critical_evidence": ["funding_type", "connectivity"],
        }
        hydrated = hydrate_confidence_display(legacy)
        self.assertEqual(
            hydrated["missing_critical_evidence_labels"],
            ["How the school is funded", "Internet reliability on site"],
        )
        self.assertEqual(hydrated["label_display"], "Provisional")
        self.assertEqual(hydrated["status_display"], "Needs confirmation")

    def test_an_unknown_evidence_key_is_humanized_rather_than_dropped(self):
        hydrated = hydrate_confidence_display(
            {"missing_critical_evidence": ["some_future_signal"]}
        )
        self.assertEqual(
            hydrated["missing_critical_evidence_labels"], ["Some future signal"]
        )

    def test_junk_input_returns_an_empty_dict_not_a_crash(self):
        for value in (None, "", 7, []):
            with self.subTest(value=value):
                self.assertEqual(hydrate_confidence_display(value), {})

    def test_no_missing_evidence_yields_an_empty_list_so_the_banner_hides(self):
        hydrated = hydrate_confidence_display({"missing_critical_evidence": []})
        self.assertEqual(hydrated["missing_critical_evidence_labels"], [])


class SurfaceContractTests(SimpleTestCase):
    """The two screens that render this envelope must read the hydrated fields."""

    def test_the_wizard_renders_labels_not_keys(self):
        source = (
            Path(settings.BASE_DIR) / "static/js/rmc-signup-wizard-v4.js"
        ).read_text(encoding="utf-8")
        self.assertIn("envelope.missing_critical_evidence_labels", source)
        # The browser-side underscore swap is what made this untranslatable.
        self.assertNotIn('missing.join(", ").replaceAll("_", " ")', source)

    def test_tenant_360_renders_labels_not_keys(self):
        source = (
            Path(settings.BASE_DIR) / "templates/schools/super_tenant_360.html"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "signup_confidence.missing_critical_evidence_labels", source
        )
        self.assertNotIn(
            'signup_confidence.missing_critical_evidence|join:", "', source
        )
        # `score_kind` is a machine constant; the envelope carries the sentence.
        self.assertIn("signup_confidence.calibration.statement", source)
        self.assertNotIn("signup_confidence.score_kind", source)
        # Every needle is a {{ }} path, and two are absences. The shell is not.
        assert_wires(self, _TN_ROOT / "templates/schools/super_tenant_360.html",
                     "control_plane_base.html")


class FullManifestTests(SimpleTestCase):
    def test_a_real_manifest_hydrates_end_to_end(self):
        manifest = build_onboarding_recommendations(
            country_code="CM",
            education_cycles=["secondary"],
            language_codes=["en"],
            institution_profile={},
        )
        hydrated = hydrate_confidence_display(manifest["confidence_envelope"])
        self.assertEqual(
            len(hydrated["missing_critical_evidence_labels"]),
            len(manifest["confidence_envelope"]["missing_critical_evidence"]),
        )
        for label in hydrated["missing_critical_evidence_labels"]:
            self.assertNotIn("_", label)
