"""Wave Q5 (v3.95.2 — 2026-05-26) — MAT registry-editor form tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.schools.forms_mat_group_hub import (
    MATGroupEditorForm,
    apply_form_to_payload,
    load_form_initial_from_payload,
)


def _valid_form_data(**overrides):
    data = {
        "group_id": "trust-1",
        "display_name": "Trust One",
        "operator_email": "ops@example.com",
        "region": "UK-North",
        "members": (
            "school-a | School A | UK-North\n"
            "school-b | School B"
        ),
    }
    data.update(overrides)
    return data


class FormValidationTests(SimpleTestCase):

    def test_valid_form(self):
        form = MATGroupEditorForm(_valid_form_data())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(len(form.cleaned_data["members"]), 2)

    def test_uppercase_group_id_rejected(self):
        form = MATGroupEditorForm(_valid_form_data(group_id="Trust-1"))
        self.assertFalse(form.is_valid())
        self.assertIn("group_id", form.errors)

    def test_spaced_group_id_rejected(self):
        form = MATGroupEditorForm(_valid_form_data(group_id="trust 1"))
        self.assertFalse(form.is_valid())

    def test_no_members_rejected(self):
        form = MATGroupEditorForm(_valid_form_data(members=""))
        self.assertFalse(form.is_valid())
        self.assertIn("members", form.errors)

    def test_member_missing_pipe_rejected(self):
        form = MATGroupEditorForm(_valid_form_data(members="just-one-token"))
        self.assertFalse(form.is_valid())

    def test_member_with_three_parts_keeps_region(self):
        form = MATGroupEditorForm(_valid_form_data(
            members="a | A School | UK-North",
        ))
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["members"][0]["region"], "UK-North")

    def test_comment_lines_skipped(self):
        form = MATGroupEditorForm(_valid_form_data(members=(
            "# this is a comment\n"
            "school-a | School A | UK-North\n"
            "\n"
            "school-b | School B | UK-North"
        )))
        self.assertTrue(form.is_valid())
        self.assertEqual(len(form.cleaned_data["members"]), 2)

    def test_delete_checkbox_skips_member_validation(self):
        form = MATGroupEditorForm(_valid_form_data(
            members="", delete="on",
        ))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["members"], [])


class PayloadRoundtripTests(SimpleTestCase):

    def test_apply_new_group(self):
        form = MATGroupEditorForm(_valid_form_data())
        self.assertTrue(form.is_valid())
        payload = apply_form_to_payload({}, form)
        self.assertIn("mat_groups", payload)
        self.assertIn("trust-1", payload["mat_groups"])
        self.assertEqual(payload["mat_groups"]["trust-1"]["display_name"],
                          "Trust One")

    def test_apply_replaces_existing(self):
        existing = {"mat_groups": {"trust-1": {"display_name": "old",
                                                  "members": []}}}
        form = MATGroupEditorForm(_valid_form_data(display_name="new"))
        self.assertTrue(form.is_valid())
        payload = apply_form_to_payload(existing, form)
        self.assertEqual(payload["mat_groups"]["trust-1"]["display_name"], "new")

    def test_apply_delete_removes_group(self):
        existing = {"mat_groups": {"trust-1": {"display_name": "old",
                                                  "members": []}}}
        form = MATGroupEditorForm(_valid_form_data(delete="on", members=""))
        self.assertTrue(form.is_valid())
        payload = apply_form_to_payload(existing, form)
        self.assertNotIn("trust-1", payload["mat_groups"])

    def test_apply_preserves_other_keys_in_payload(self):
        existing = {
            "mat_groups": {},
            "other_key": "value",
            "nested": {"k": "v"},
        }
        form = MATGroupEditorForm(_valid_form_data())
        self.assertTrue(form.is_valid())
        payload = apply_form_to_payload(existing, form)
        self.assertEqual(payload["other_key"], "value")
        self.assertEqual(payload["nested"], {"k": "v"})


class LoadInitialTests(SimpleTestCase):

    def test_load_existing(self):
        payload = {"mat_groups": {"trust-1": {
            "display_name": "Trust One",
            "operator_email": "ops@x.com",
            "region": "UK",
            "members": [
                {"tenant_slug": "a", "display_name": "A", "region": "UK"},
                {"tenant_slug": "b", "display_name": "B", "region": ""},
            ],
        }}}
        initial = load_form_initial_from_payload(payload, "trust-1")
        self.assertEqual(initial["display_name"], "Trust One")
        self.assertIn("a | A | UK", initial["members"])
        self.assertIn("b | B", initial["members"])

    def test_load_missing_returns_empty_form(self):
        initial = load_form_initial_from_payload({}, "nonexistent")
        self.assertEqual(initial["display_name"], "")
        self.assertEqual(initial["members"], "")
