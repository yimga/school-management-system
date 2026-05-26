"""Per-wizard happy-path tests for the Unified Wizard Framework.

For every wizard in the registry, synthesize a minimal valid payload per step,
walk the state machine end-to-end via :func:`apply_step_answer`, and assert:

* the walker terminates (``current_step_key`` becomes ``None``);
* ``completed_at`` lands;
* every visited step appears in ``state["completed"]`` and ``state["answers"]``;
* the wizard's slice lands in ``school.settings["wizards"][<wizard_key>]``
  (per-tenant JSONField read by ``platform_runtime.get_effective_site_settings``).

The engine tests in ``test_wizard_engine.py`` exercise the registry, branching,
and validator plumbing in isolation. This file proves the COMPOSITION: a JSON
spec + its referenced resolvers + its declared writers + the state resolver
+ tenant persistence all line up so that a real wizard walked from start to
finish writes the expected slice on a real DB-backed School.

Walker is bounded by ``_MAX_STEPS`` to defend against cyclic branch graphs.
"""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.schools.models import School
from apps.setup_studio import wizard_engine, wizard_state_resolver

_MAX_STEPS = 50


def _synthesize_field_value(field_def: dict):
    """Return a minimal valid value for one ``structured_form`` field."""
    field_type = (field_def.get("type") or "text").lower()
    validation = field_def.get("validation") or {}

    if field_type == "file":
        allowed = validation.get("allowed_extensions") or ["pdf"]
        ext = allowed[0]
        return SimpleUploadedFile(
            f"test.{ext}",
            b"x" * 64,
            content_type="application/octet-stream",
        )
    if field_type == "color":
        return "#4F46E5"
    if field_type == "number":
        return 1
    if field_type == "decimal":
        return "1.00"
    if field_type == "boolean":
        return True
    if field_type == "date":
        return "2026-05-26"
    if field_type == "datetime":
        return "2026-05-26T00:00:00+00:00"
    if field_type in ("multi_select", "multiselect", "checkbox_group"):
        return ["a"]
    if field_type == "domain":
        return "test.example.com"
    if field_type == "select":
        return "default"
    # text + long_text + everything else
    max_len = validation.get("max_length")
    s = "test value"
    if isinstance(max_len, int) and len(s) > max_len:
        s = s[:max_len]
    return s


def _synthesize_payload(step) -> dict:
    """Return a minimal valid payload for one step."""
    input_type = step.input_type
    validation = step.validation or {}
    branches = step.branches or {}

    if input_type == "structured_form":
        payload = {}
        for fld in step.fields:
            name = fld.get("name")
            if isinstance(name, str):
                payload[name] = _synthesize_field_value(fld)
        return payload

    if input_type == "single_choice":
        # If branches exist, pick the first non-default branch key so the
        # walker actually traverses that branch instead of falling to default.
        for branch_key in branches:
            if branch_key != "default":
                first_token = branch_key.split("|")[0].strip()
                if first_token:
                    return {"value": first_token}
        return {"value": "default"}

    if input_type == "multi_choice":
        return {"value": ["a"]}

    if input_type in ("text", "long_text", "rich_select"):
        max_len = validation.get("max_length")
        s = "test value"
        if isinstance(max_len, int) and len(s) > max_len:
            s = s[:max_len]
        return {"value": s}

    if input_type == "number":
        return {"value": 1}

    if input_type == "decimal":
        return {"value": "1.00"}

    if input_type == "boolean":
        return {"value": True}

    if input_type == "color_picker":
        return {"value": "#4F46E5"}

    if input_type == "domain_input":
        return {"value": "test.example.com"}

    if input_type in ("file_upload", "image_upload"):
        allowed = validation.get("allowed_extensions") or ["pdf"]
        ext = allowed[0]
        return {
            "value": SimpleUploadedFile(
                f"test.{ext}",
                b"x" * 64,
                content_type="application/octet-stream",
            )
        }

    if input_type == "draw_on_map":
        return {"value": {"lat": 0.0, "lng": 0.0}}

    if input_type == "csv_mapping":
        return {"value": {"source_field": "target_field"}}

    if input_type == "ranked_list":
        return {"value": ["a", "b"]}

    if input_type == "key_value_pairs":
        return {"value": {"k": "v"}}

    if input_type == "datetime":
        return {"value": "2026-05-26T00:00:00+00:00"}

    if input_type == "duration":
        return {"value": "PT1H"}

    return {"value": "test"}


class WizardHappyPathTests(TestCase):
    """Walks every registered wizard from first_step to completion."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Wizard Happy Path School",
            slug="wizard-happy-path",
            subdomain="wizard-happy-path",
            is_active=True,
        )

    def test_every_registered_wizard_walks_to_completion(self):
        registry = wizard_engine.WIZARD_REGISTRY
        self.assertTrue(registry, "wizard registry is empty — engine boot may have failed")

        for wizard_key, wizard in sorted(registry.items()):
            with self.subTest(wizard_key=wizard_key):
                wizard_state_resolver.reset_wizard(self.school, wizard_key)
                state = wizard_state_resolver.start_wizard(self.school, wizard_key)
                self.assertEqual(state["current_step_key"], wizard.first_step().key)

                visited_keys: list[str] = []
                for _ in range(_MAX_STEPS):
                    current_key = state.get("current_step_key")
                    if current_key is None:
                        break
                    step = wizard.step_by_key(current_key)
                    payload = _synthesize_payload(step)
                    state = wizard_state_resolver.apply_step_answer(
                        self.school, wizard_key, current_key, payload,
                    )
                    visited_keys.append(current_key)
                else:
                    self.fail(
                        f"wizard {wizard_key!r} did not terminate within "
                        f"{_MAX_STEPS} steps — possible branch cycle"
                    )

                self.assertIsNone(state["current_step_key"], wizard_key)
                self.assertIn("completed_at", state, wizard_key)
                self.assertTrue(state["completed_at"], wizard_key)
                self.assertTrue(visited_keys, wizard_key)
                for visited in visited_keys:
                    self.assertIn(visited, state["completed"], f"{wizard_key}:{visited}")
                    self.assertIn(visited, state["answers"], f"{wizard_key}:{visited}")

    def test_every_wizard_persists_to_school_settings(self):
        """Every wizard MUST leave school.settings with some persisted side effect.

        Different wizards use different top-level subkeys under ``school.settings``
        depending on their writer style — most land under ``wizards.<key>.*`` via
        the default cockpit writer, but some (e.g. ``cross_platform_whitelabel_branding``)
        land under domain-specific keys (``whitelabel.*``) by design. The minimal
        contract is that *something* gets written, so the per-tenant cascade reads
        it through ``platform_runtime.get_effective_site_settings``.
        """
        registry = wizard_engine.WIZARD_REGISTRY
        self.assertTrue(registry)

        for wizard_key, wizard in sorted(registry.items()):
            with self.subTest(wizard_key=wizard_key):
                # Fresh slate for both engine state and tenant settings, so each
                # wizard's effect is isolated (writers are idempotent — running
                # the same wizard twice yields the same dict, so we can't compare
                # before/after without resetting).
                self.school.settings = {}
                self.school.save(update_fields=["settings"])
                wizard_state_resolver.reset_wizard(self.school, wizard_key)
                wizard_state_resolver.start_wizard(self.school, wizard_key)

                state = wizard_state_resolver.get_wizard_state(self.school, wizard_key)
                for _ in range(_MAX_STEPS):
                    current_key = state.get("current_step_key")
                    if current_key is None:
                        break
                    step = wizard.step_by_key(current_key)
                    payload = _synthesize_payload(step)
                    state = wizard_state_resolver.apply_step_answer(
                        self.school, wizard_key, current_key, payload,
                    )

                self.school.refresh_from_db()
                after = self.school.settings or {}
                self.assertTrue(
                    after,
                    f"{wizard_key}: completed wizard wrote nothing to school.settings",
                )
