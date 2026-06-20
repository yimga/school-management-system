"""Unit tests for wizard_engine — registry, branching, validation."""

import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.setup_studio import wizard_engine


_VALID_WIZARD = {
    "wizard_key": "test_wizard",
    "version": 1,
    "audience": ["tenant_admin"],
    "label_token": "wizards.test_wizard.label",
    "description_token": "wizards.test_wizard.description",
    "icon_class": "rmc-icon-test",
    "estimated_minutes": 5,
    "ai": {"smart_defaults": False},
    "steps": [
        {
            "key": "step_one",
            "label_token": "wizards.test_wizard.step.step_one.label",
            "input_type": "single_choice",
            "validation": {"required": True},
        },
        {
            "key": "step_two",
            "label_token": "wizards.test_wizard.step.step_two.label",
            "input_type": "text",
            "validation": {"required": True, "max_length": 50},
        },
    ],
}


class RegistryLoadTests(SimpleTestCase):
    def test_load_valid_wizard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test_wizard.json"
            path.write_text(json.dumps(_VALID_WIZARD), encoding="utf-8")
            registry = wizard_engine.load_wizard_registry(Path(tmp))
            self.assertIn("test_wizard", registry)
            wizard = registry["test_wizard"]
            self.assertEqual(len(wizard.steps), 2)
            self.assertEqual(wizard.audience, ("tenant_admin",))

    def test_skip_underscore_prefixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "_draft.json"
            path.write_text(json.dumps(_VALID_WIZARD), encoding="utf-8")
            registry = wizard_engine.load_wizard_registry(Path(tmp))
            self.assertNotIn("test_wizard", registry)

    def test_skip_feature_flag_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            disabled = dict(_VALID_WIZARD)
            disabled["feature_flag_disabled"] = True
            path = Path(tmp) / "test_wizard.json"
            path.write_text(json.dumps(disabled), encoding="utf-8")
            registry = wizard_engine.load_wizard_registry(Path(tmp))
            self.assertNotIn("test_wizard", registry)

    def test_invalid_json_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text("{ not valid json", encoding="utf-8")
            # Should not raise
            registry = wizard_engine.load_wizard_registry(Path(tmp))
            self.assertEqual(registry, {})


class SchemaTests(SimpleTestCase):
    def test_missing_wizard_key_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = dict(_VALID_WIZARD)
            del bad["wizard_key"]
            path = Path(tmp) / "missing_key.json"
            path.write_text(json.dumps(bad), encoding="utf-8")
            registry = wizard_engine.load_wizard_registry(Path(tmp))
            self.assertEqual(registry, {})

    def test_empty_audience_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = dict(_VALID_WIZARD)
            bad["audience"] = []
            path = Path(tmp) / "empty_audience.json"
            path.write_text(json.dumps(bad), encoding="utf-8")
            registry = wizard_engine.load_wizard_registry(Path(tmp))
            self.assertEqual(registry, {})

    def test_branches_and_resolver_both_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = dict(_VALID_WIZARD)
            bad["steps"] = [
                {
                    "key": "step_one",
                    "label_token": "...",
                    "input_type": "single_choice",
                    "branches": {"a": "step_two"},
                    "next_step_resolver": "apps.foo::bar",
                },
                {"key": "step_two", "label_token": "...", "input_type": "text"},
            ]
            path = Path(tmp) / "conflict.json"
            path.write_text(json.dumps(bad), encoding="utf-8")
            registry = wizard_engine.load_wizard_registry(Path(tmp))
            self.assertEqual(registry, {})


class AudienceFilterTests(SimpleTestCase):
    def test_list_for_audience(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "tenant_wiz.json").write_text(
                json.dumps({**_VALID_WIZARD, "wizard_key": "tenant_wiz", "audience": ["tenant_admin"]}),
                encoding="utf-8",
            )
            (Path(tmp) / "operator_wiz.json").write_text(
                json.dumps({**_VALID_WIZARD, "wizard_key": "operator_wiz", "audience": ["operator"]}),
                encoding="utf-8",
            )
            (Path(tmp) / "both_wiz.json").write_text(
                json.dumps({**_VALID_WIZARD, "wizard_key": "both_wiz", "audience": ["operator", "tenant_admin"]}),
                encoding="utf-8",
            )
            wizard_engine.load_wizard_registry(Path(tmp))
            tenant = wizard_engine.list_wizards_for_audience("tenant_admin")
            keys = {w.wizard_key for w in tenant}
            self.assertIn("tenant_wiz", keys)
            self.assertIn("both_wiz", keys)
            self.assertNotIn("operator_wiz", keys)


class BranchingTests(SimpleTestCase):
    def setUp(self):
        self.wizard = wizard_engine._parse_wizard({
            "wizard_key": "branching_test",
            "version": 1,
            "audience": ["operator"],
            "steps": [
                {
                    "key": "first",
                    "input_type": "single_choice",
                    "branches": {"BR|IN": "second_a", "default": "second_b"},
                },
                {"key": "second_a", "input_type": "text"},
                {"key": "second_b", "input_type": "text"},
            ],
        }, Path("/tmp/branching_test.json"))

    def test_branch_match(self):
        next_step = wizard_engine.resolve_next_step(
            self.wizard,
            current_step=self.wizard.steps[0],
            current_answer={"value": "BR"},
        )
        self.assertEqual(next_step.key, "second_a")

    def test_branch_default(self):
        next_step = wizard_engine.resolve_next_step(
            self.wizard,
            current_step=self.wizard.steps[0],
            current_answer={"value": "US"},
        )
        self.assertEqual(next_step.key, "second_b")

    def test_branch_pipe_alternative(self):
        next_step = wizard_engine.resolve_next_step(
            self.wizard,
            current_step=self.wizard.steps[0],
            current_answer={"value": "IN"},
        )
        self.assertEqual(next_step.key, "second_a")

    def test_branch_end(self):
        wizard = wizard_engine._parse_wizard({
            "wizard_key": "end_test",
            "version": 1,
            "audience": ["operator"],
            "steps": [
                {"key": "one", "input_type": "single_choice", "branches": {"default": "__end__"}},
            ],
        }, Path("/tmp/end_test.json"))
        next_step = wizard_engine.resolve_next_step(
            wizard,
            current_step=wizard.steps[0],
            current_answer={"value": "x"},
        )
        self.assertIsNone(next_step)


class SequentialAdvanceTests(SimpleTestCase):
    def test_advances_to_next(self):
        wizard = wizard_engine._parse_wizard(_VALID_WIZARD, Path("/tmp/seq.json"))
        next_step = wizard_engine.resolve_next_step(
            wizard,
            current_step=wizard.steps[0],
            current_answer={"value": "x"},
        )
        self.assertEqual(next_step.key, "step_two")

    def test_final_step_returns_none(self):
        wizard = wizard_engine._parse_wizard(_VALID_WIZARD, Path("/tmp/seq.json"))
        next_step = wizard_engine.resolve_next_step(
            wizard,
            current_step=wizard.steps[-1],
            current_answer={"value": "x"},
        )
        self.assertIsNone(next_step)


class ValidationTests(SimpleTestCase):
    def test_simple_required_fail(self):
        wizard = wizard_engine._parse_wizard(_VALID_WIZARD, Path("/tmp/v.json"))
        step = wizard.steps[0]
        is_valid, errors = wizard_engine.validate_step_answer(step, {"value": None})
        self.assertFalse(is_valid)
        self.assertIn("value", errors)

    def test_simple_pass(self):
        wizard = wizard_engine._parse_wizard(_VALID_WIZARD, Path("/tmp/v.json"))
        step = wizard.steps[0]
        is_valid, errors = wizard_engine.validate_step_answer(step, {"value": "x"})
        self.assertTrue(is_valid)
        self.assertEqual(errors, {})

    def test_structured_form_validation(self):
        wizard = wizard_engine._parse_wizard({
            "wizard_key": "sf",
            "version": 1,
            "audience": ["operator"],
            "steps": [
                {
                    "key": "form",
                    "input_type": "structured_form",
                    "fields": [
                        {"name": "name", "type": "text", "required": True, "validation": {"max_length": 5}},
                    ],
                },
            ],
        }, Path("/tmp/sf.json"))
        step = wizard.steps[0]
        ok, errs = wizard_engine.validate_step_answer(step, {"name": ""})
        self.assertFalse(ok)
        self.assertIn("name", errs)
        ok, errs = wizard_engine.validate_step_answer(step, {"name": "abcdefg"})
        self.assertFalse(ok)
        ok, errs = wizard_engine.validate_step_answer(step, {"name": "abc"})
        self.assertTrue(ok)

    def test_global_text_cap_bounds_undeclared_field(self):
        """A free-text field with NO declared max_length still can't write an
        unbounded string into stored state."""
        wizard = wizard_engine._parse_wizard({
            "wizard_key": "cap_sf",
            "version": 1,
            "audience": ["operator"],
            "steps": [
                {
                    "key": "form",
                    "input_type": "structured_form",
                    "fields": [{"name": "notes", "type": "text"}],
                },
            ],
        }, Path("/tmp/cap_sf.json"))
        step = wizard.steps[0]
        over = "x" * (wizard_engine.WIZARD_MAX_TEXT_FIELD_LENGTH + 1)
        ok, errs = wizard_engine.validate_step_answer(step, {"notes": over})
        self.assertFalse(ok)
        self.assertEqual(errs.get("notes"), "wizards.errors.text_too_long")
        ok, _ = wizard_engine.validate_step_answer(step, {"notes": "a reasonable note"})
        self.assertTrue(ok)

    def test_explicit_max_length_overrides_global_cap(self):
        """An author-declared max_length larger than nothing still owns the bound
        — the global backstop does not double-reject what the field already passed."""
        wizard = wizard_engine._parse_wizard(_VALID_WIZARD, Path("/tmp/v.json"))
        step = wizard.steps[1]  # text field, max_length=50
        ok, errs = wizard_engine.validate_step_answer(step, {"value": "ok"})
        self.assertTrue(ok)
        ok, errs = wizard_engine.validate_step_answer(step, {"value": "z" * 51})
        self.assertFalse(ok)
        self.assertEqual(errs.get("value"), "wizards.errors.max_length")

    def test_global_text_cap_bounds_simple_value(self):
        wizard = wizard_engine._parse_wizard({
            "wizard_key": "cap_simple",
            "version": 1,
            "audience": ["operator"],
            "steps": [{"key": "free", "input_type": "text"}],
        }, Path("/tmp/cap_simple.json"))
        step = wizard.steps[0]
        over = "y" * (wizard_engine.WIZARD_MAX_TEXT_FIELD_LENGTH + 1)
        ok, errs = wizard_engine.validate_step_answer(step, {"value": over})
        self.assertFalse(ok)
        self.assertEqual(errs.get("value"), "wizards.errors.text_too_long")

    def test_unexpected_field_rejected(self):
        """Structured-form payloads carrying keys outside the declared field set
        are rejected at the apply_step_answer boundary (defense-in-depth)."""
        wizard = wizard_engine._parse_wizard({
            "wizard_key": "strict_sf",
            "version": 1,
            "audience": ["operator"],
            "steps": [
                {
                    "key": "form",
                    "input_type": "structured_form",
                    "fields": [{"name": "school_name", "type": "text", "required": True}],
                },
            ],
        }, Path("/tmp/strict_sf.json"))
        step = wizard.steps[0]
        ok, errs = wizard_engine.validate_step_answer(
            step, {"school_name": "Westside High", "is_staff": True}
        )
        self.assertFalse(ok)
        self.assertEqual(errs.get("is_staff"), "wizards.errors.unexpected_field")
        # Declared-only payload still passes.
        ok, _ = wizard_engine.validate_step_answer(step, {"school_name": "Westside High"})
        self.assertTrue(ok)

    def _nonstructured_step(self, input_type, validation=None):
        wizard = wizard_engine._parse_wizard({
            "wizard_key": f"ns_{input_type}",
            "version": 1,
            "audience": ["operator"],
            "steps": [{
                "key": "s",
                "input_type": input_type,
                "validation": validation or {},
            }],
        }, Path(f"/tmp/ns_{input_type}.json"))
        return wizard.steps[0]

    def test_unexpected_field_rejected_on_nonstructured(self):
        """A non-structured step (text/single_choice/etc.) only carries ``value``.
        A smuggled extra key is rejected just like on structured_form."""
        step = self._nonstructured_step("text")
        ok, errs = wizard_engine.validate_step_answer(
            step, {"value": "ok", "is_superuser": True}
        )
        self.assertFalse(ok)
        self.assertEqual(errs.get("is_superuser"), "wizards.errors.unexpected_field")
        # Plain ``value`` payload still passes.
        ok, _ = wizard_engine.validate_step_answer(step, {"value": "ok"})
        self.assertTrue(ok)

    def test_key_value_pairs_allows_pairs_and_value(self):
        """key_value_pairs legitimately uses ``pairs`` (HTTP) or ``value`` (synth);
        both pass, but a foreign key is still rejected."""
        step = self._nonstructured_step("key_value_pairs")
        ok, _ = wizard_engine.validate_step_answer(step, {"pairs": [{"key": "a", "value": "b"}]})
        self.assertTrue(ok)
        ok, _ = wizard_engine.validate_step_answer(step, {"value": {"a": "b"}})
        self.assertTrue(ok)
        ok, errs = wizard_engine.validate_step_answer(step, {"pairs": [], "evil": 1})
        self.assertFalse(ok)
        self.assertEqual(errs.get("evil"), "wizards.errors.unexpected_field")

    def test_duration_allows_part_keys(self):
        """duration legitimately uses days/hours/minutes (HTTP) or ``value`` (synth)."""
        step = self._nonstructured_step("duration")
        ok, _ = wizard_engine.validate_step_answer(step, {"days": 1, "hours": 2, "minutes": 0})
        self.assertTrue(ok)
        ok, _ = wizard_engine.validate_step_answer(step, {"value": "PT1H"})
        self.assertTrue(ok)
        ok, errs = wizard_engine.validate_step_answer(step, {"days": 1, "seconds": 5})
        self.assertFalse(ok)
        self.assertEqual(errs.get("seconds"), "wizards.errors.unexpected_field")


class SanitizeStorageCapTests(SimpleTestCase):
    """The universal free-text backstop bounds EVERY stored string, including
    nested ones (key_value_pairs ``pairs``, csv_mapping dicts, list items) that
    validate_step_answer's declared-path cap never reaches."""

    def setUp(self):
        from apps.setup_studio import wizard_state_resolver
        self.sanitize = wizard_state_resolver._sanitize_for_storage
        self.cap = wizard_engine.WIZARD_MAX_TEXT_FIELD_LENGTH

    def test_key_value_pairs_nested_string_truncated(self):
        payload = {"pairs": [{"key": "policy", "value": "x" * (self.cap + 5000)}]}
        out = self.sanitize(payload)
        self.assertEqual(len(out["pairs"][0]["value"]), self.cap)
        self.assertEqual(out["pairs"][0]["key"], "policy")  # short key untouched

    def test_list_and_dict_items_truncated(self):
        big = "y" * (self.cap + 1)
        out = self.sanitize({"value": [big, "ok"], "nested": {"deep": big}})
        self.assertEqual(len(out["value"][0]), self.cap)
        self.assertEqual(out["value"][1], "ok")
        self.assertEqual(len(out["nested"]["deep"]), self.cap)

    def test_within_cap_unchanged(self):
        payload = {"pairs": [{"key": "a", "value": "a reasonable value"}]}
        self.assertEqual(self.sanitize(payload), payload)


class GetWizardTests(SimpleTestCase):
    def test_not_found_raises(self):
        with self.assertRaises(wizard_engine.WizardNotFound):
            wizard_engine.get_wizard("non_existent_wizard_xyz")
