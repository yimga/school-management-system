"""Compliance erasure form: draft-save + i18n wiring (template regression).

WHAT CHANGED AND WHY THIS TEST WAS REWRITTEN
--------------------------------------------
This asserted the literal string ``FormDraftSave.init`` appeared in the template,
which was the correct contract when every page had to call it from its own
``<script>``. ``static/js/form-draft-save.js`` now ends with a CSP-clean
auto-init that walks ``form[data-draft-key]`` on DOMContentLoaded, and its own
comment says the per-page shims are no longer required -- so the templates dropped
the call.

The old assertion did not merely become obsolete, it became MISLEADING: the sibling
parent templates satisfy ``assertIn("FormDraftSave.init")`` only because they carry
a ``{% comment %}`` that happens to mention the function by name. So the assertion
was green on pages whose wiring it never checked, and red on this one for having
less prose -- the exact inversion of what it was written to catch.

What actually has to hold now is the pair: the library is loaded, and the form
opts in with ``data-draft-key``. Both are asserted here, plus the auto-init hook
in the library itself -- because if that hook is ever removed, every template that
dropped its explicit call goes silently dead, and this file is the regression seal
for exactly that.
"""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class ErasureRequestTemplateTests(SimpleTestCase):
    def _template(self) -> str:
        return (
            Path(settings.BASE_DIR)
            / "templates"
            / "compliance"
            / "erasure_request.html"
        ).read_text(encoding="utf-8")

    def test_template_loads_the_draft_save_library(self):
        self.assertIn("form-draft-save.js", self._template())

    def test_the_form_opts_in_with_a_draft_key(self):
        text = self._template()
        self.assertIn('data-draft-key="compliance_erasure_', text)
        # The key must be per-school, or two schools share one browser-local draft.
        self.assertIn('data-draft-key="compliance_erasure_{{ school.id }}"', text)

    def test_the_library_auto_inits_opted_in_forms(self):
        """The hook the templates now rely on instead of a per-page call.

        Without this, `data-draft-key` is inert markup and every draft-save form
        on the platform stops saving -- with no error anywhere.
        """
        lib = (
            Path(settings.BASE_DIR) / "static" / "js" / "form-draft-save.js"
        ).read_text(encoding="utf-8")
        self.assertIn("form[data-draft-key]", lib)
        self.assertIn("_autoInitFormDraftSave", lib)
        self.assertIn("DOMContentLoaded", lib)

    def test_the_library_is_loaded_before_the_form_would_be_submitted(self):
        """A script tag after the form is fine; one that never runs is not."""
        text = self._template()
        self.assertLess(
            text.index('data-draft-key="compliance_erasure_'),
            text.index("form-draft-save.js"),
            "the opt-in attribute is expected on the form, with the library "
            "loaded at the end of the page",
        )
