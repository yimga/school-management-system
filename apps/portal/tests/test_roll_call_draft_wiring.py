"""Wave 6 / RESILIENT_EDGE: roll-call POST forms wired to form-draft-save.js."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class RollCallDraftTemplateTests(SimpleTestCase):
    """Source-level regression: draft keys must stay on POST forms (no full portal_base render)."""

    def test_student_roll_call_template_has_draft_key_expression(self):
        root = Path(settings.BASE_DIR)
        text = (root / "templates" / "portal" / "roll_call_student.html").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'data-draft-key="student_roll_{{ classroom.id }}_{{ date_value }}"',
            text,
        )
        self.assertIn("form-draft-save.js", text)
        self.assertIn("FormDraftSave.init", text)

    def test_teacher_roll_call_template_has_draft_key_expression(self):
        root = Path(settings.BASE_DIR)
        text = (root / "templates" / "portal" / "roll_call_teacher.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-draft-key="teacher_roll_{{ date_value }}"', text)
        self.assertIn("form-draft-save.js", text)
