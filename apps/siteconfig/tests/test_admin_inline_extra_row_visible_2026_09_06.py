"""An ``extra=`` inline row a user cannot see is a row they cannot fill.

Unfold stamps ``class="template"`` on EVERY inline form that has no ``original``
(``unfold/templates/admin/edit_inline/tabular.html``) -- the real ``extra=`` rows
as well as the ``__prefix__`` prototype. Nothing else separates them but the
prototype's own ``tr.empty-form``. A rule keyed on ``tbody.template`` therefore
hides the row the admin just offered.

Measured in Chromium over CDP on ``people.StudentProfile`` /add (2026-09-06):
tbody ``guardian_links-0``, holding 12 live inputs, computed ``display: none``
while the column head above it painted. The "Add student" form showed a guardian
table with a header and nothing under it to type into. A guardian could only be
attached after saving the student, never through the add form itself.

The companion invariant is the head. Unfold's tabular head carries
``hidden lg:table-header-group`` and re-prints each column name into its own cell
through ``::before`` below ``lg``. A shell-wide rule that force-shows ``thead``
without honouring that ``hidden`` leaves BOTH layers painted under 1024px -- the
doubled header row. Measured at 900px: two header layers before, one after. A
desktop browser at 125% zoom is already under 1024 CSS px, so this is not a
phone-only path.

Static by design. Which rule WINS is a browser question and is not what this
pins. It pins the two textual invariants that make the collapse impossible:
nothing hides a bare ``tbody.template``, and no shell-wide ``thead`` force
overrides an explicit ``hidden``. Both are scanned across every stylesheet, not
only the two that regressed, so a new sheet cannot reintroduce either.
"""

from __future__ import annotations

import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CSS_DIR = REPO_ROOT / "static" / "css"

SHELL_ROOT = '[data-rmc-shell-root="django-admin"]'


def _strip_comments(source: str) -> str:
    """Blank out ``/* */`` comments.

    Both fixes are commented, and those comments name ``tbody.template`` and
    ``thead`` in prose. A scanner that reads comments reports the very defect
    the comment records as fixed.
    """
    return re.sub(r"/\*.*?\*/", " ", source, flags=re.S)


def _rules(source: str):
    """Yield ``(selector, declarations)`` for each rule.

    ``[^{}]`` cannot span a brace, so an at-rule preamble never attaches itself
    to the rule nested inside it; the nested rule is matched on its own.
    """
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", source):
        yield match.group(1).strip(), match.group(2)


def _stylesheets():
    return sorted(CSS_DIR.rglob("*.css"))


class InlineExtraRowStaysVisibleTests(unittest.TestCase):
    def test_stylesheets_are_present(self):
        """A silent zero from an empty scan would pass every test below."""
        sheets = _stylesheets()
        self.assertGreater(len(sheets), 50, "static/css did not resolve")
        names = {path.name for path in sheets}
        for required in (
            "rmc-admin-django-canvas-contract.css",
            "rmc-admin-emergency-full-canvas-v17.css",
        ):
            self.assertIn(required, names)

    def test_no_rule_hides_a_bare_template_tbody(self):
        """``tbody.template`` is every NEW row, not the prototype."""
        offenders = []
        for sheet in _stylesheets():
            source = _strip_comments(sheet.read_text(encoding="utf-8", errors="replace"))
            for selector, declarations in _rules(source):
                if not re.search(r"display\s*:\s*none", declarations):
                    continue
                for one in selector.split(","):
                    if "tbody.template" in one:
                        offenders.append("%s: %s" % (sheet.name, " ".join(one.split())))
        self.assertEqual(
            offenders,
            [],
            "these hide every extra= inline row, not just the prototype: %s"
            % offenders,
        )

    def test_the_prototype_row_is_still_hidden(self):
        """Narrowing the selector must not un-hide the phantom fillable line."""
        by_tr = []
        by_tbody = []
        for sheet in _stylesheets():
            source = _strip_comments(sheet.read_text(encoding="utf-8", errors="replace"))
            for selector, declarations in _rules(source):
                if not re.search(r"display\s*:\s*none", declarations):
                    continue
                for one in selector.split(","):
                    if "tbody:has(> tr.empty-form)" in one:
                        by_tbody.append(sheet.name)
                    elif "tr.empty-form" in one:
                        by_tr.append(sheet.name)
        self.assertTrue(by_tr, "nothing hides tr.empty-form any more")
        self.assertTrue(by_tbody, "nothing hides the prototype at tbody level")

    def test_shell_wide_thead_force_honours_hidden(self):
        """A force must not resurrect what the markup deliberately hid.

        Changelist heads (``#result_list``) carry no ``hidden`` class and are
        exempt: forcing those is the reason these rules exist at all.
        """
        offenders = []
        for sheet in _stylesheets():
            source = _strip_comments(sheet.read_text(encoding="utf-8", errors="replace"))
            for selector, declarations in _rules(source):
                if not re.search(r"display\s*:\s*table-header-group", declarations):
                    continue
                for one in selector.split(","):
                    if "thead" not in one or SHELL_ROOT not in one:
                        continue
                    if "#result_list" in one:
                        continue
                    if ":not(.hidden)" in one:
                        continue
                    offenders.append("%s: %s" % (sheet.name, " ".join(one.split())))
        self.assertEqual(
            offenders,
            [],
            "these force a hidden tabular-inline head back on, doubling the "
            "header row below lg: %s" % offenders,
        )


if __name__ == "__main__":
    unittest.main()
