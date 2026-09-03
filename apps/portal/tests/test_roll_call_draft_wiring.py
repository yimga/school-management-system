"""Wave 6 / RESILIENT_EDGE: roll-call POST forms wired to form-draft-save.js."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup


class RollCallDraftTemplateTests(SimpleTestCase):
    """Source-level regression: draft keys must stay on POST forms (no full portal_base render)."""

    def test_student_roll_call_template_has_draft_key_expression(self):
        root = Path(settings.BASE_DIR)
        path = root / "templates" / "portal" / "roll_call_student.html"
        text = path.read_text(encoding="utf-8")
        # The full key is an EXPRESSION -- it embeds {{ classroom.id }} and
        # {{ date_value }} -- so only a source read can check its exact shape.
        self.assertIn(
            'data-draft-key="student_roll_{{ classroom.id }}_{{ date_value }}"',
            text,
        )
        # Its stable prefix IS a real TextNode, so ask the engine whether the
        # form still emits a draft key at all. This is the bound template.
        assert_markup(self, path, 'data-draft-key="student_roll_')
        # form-draft-save.js is a {% static %} argument -- source read only.
        self.assertIn("form-draft-save.js", text)
        # NOTE (2026-09-01): the ONLY occurrence of "FormDraftSave.init" in this
        # template is prose inside a {% comment %} on line 137, saying the page
        # script calls it. The assertion below therefore proves nothing today,
        # mutation or not. Left exactly as it is: whether the template should
        # call init, or this should assert the page script instead, is a
        # behaviour decision rather than a test-soundness one.
        self.assertIn("FormDraftSave.init", text)

    def test_teacher_roll_call_template_has_draft_key_expression(self):
        root = Path(settings.BASE_DIR)
        path = root / "templates" / "portal" / "roll_call_teacher.html"
        text = path.read_text(encoding="utf-8")
        self.assertIn('data-draft-key="teacher_roll_{{ date_value }}"', text)
        assert_markup(self, path, 'data-draft-key="teacher_roll_')
        # form-draft-save.js is a {% static %} argument -- source read only.
        self.assertIn("form-draft-save.js", text)
