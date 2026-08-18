"""Tenant /admin/ must define the utility classes its own markup depends on.

``templates/admin/base_site.html`` loads Bootstrap behind a host guard::

    {% if is_manager_host %}
    <link rel="stylesheet" href="{% static 'vendor/bootstrap/css/bootstrap.min.css' %}">
    {% endif %}

Only the OPERATOR admin gets that sheet. The tenant admin gets Unfold's
``styles.css`` (Tailwind — ships neither class) plus ~45 RMC sheets (none of
which define them either). So on tenant ``/admin/`` two classes silently
resolve to nothing:

``.visually-hidden``
    ``admin/base.html`` opens ``{% block base %}`` with a
    ``rmc-empty-state-sentinel`` marker whose whole contract is being invisible —
    ``rmc-class-grammar.css`` even says so in a comment: "``.visually-hidden``
    does the hiding." With the class undefined the sentinel becomes an ordinary
    block element and reserves vertical space at the very top of every admin
    page. Sixteen more such elements sit in the core chain.

``.d-none``
    The campus switcher renders ``class="rmc-campus-switcher d-none"`` with a
    ``disabled`` select reading "Loading schools…", and JS removes ``d-none``
    only once ``/api/v1/me/schools`` answers with more than one school. With the
    class undefined the placeholder is visible from first paint and NEVER goes
    away on a single-school tenant — the switcher is not loading, it is finished
    and hidden by a rule that does not exist.

Both defects are one root cause, and both were visible on a live tenant: a tall
blank band above the content and a permanent "Loading schools…" in the Utilities
panel.

The rule pinned here: a class the tenant admin's own templates rely on for
correctness must be defined in a stylesheet the tenant admin actually loads.
Operator ``/admin/`` is unaffected — it loads Bootstrap — and these tests assert
that asymmetry stays closed rather than merely documented.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

_BASE_SITE = Path("templates/admin/base_site.html")
_ADMIN_BASE = Path("templates/admin/base.html")
_UTILITIES = Path("templates/components/rmc_tenant_header_utilities.html")

_STATIC_RE = re.compile(r"""\{%\s*static\s+['"]([^'"]+\.css)['"]""")
_IF_RE = re.compile(r"\{%\s*if\s+(.+?)\s*%\}")
_ELSE_RE = re.compile(r"\{%\s*else\s*%\}")
_ENDIF_RE = re.compile(r"\{%\s*endif\s*%\}")


def _tenant_reachable_stylesheets(template: Path) -> list[str]:
    """CSS paths reachable when ``is_manager_host`` is falsey.

    Walks the template tracking ``{% if %}``/``{% else %}``/``{% endif %}`` depth so a
    sheet loaded only inside a manager-host branch is excluded, exactly as the
    renderer would.
    """
    sheets: list[str] = []
    # Each frame is True when the branch currently being read is manager-only.
    stack: list[bool] = []
    for raw in template.read_text(encoding="utf-8").splitlines():
        if _ENDIF_RE.search(raw):
            if stack:
                stack.pop()
            continue
        if _ELSE_RE.search(raw) and stack:
            stack[-1] = not stack[-1]
            continue
        match = _IF_RE.search(raw)
        if match:
            condition = match.group(1).strip()
            stack.append(condition == "is_manager_host")
            continue
        if any(stack):
            continue
        sheets.extend(_STATIC_RE.findall(raw))
    return sheets


_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _defines(css_text: str, selector: str) -> bool:
    """True when ``selector`` is defined as its own rule, not merely mentioned.

    Two things are NOT definitions and both occur in this codebase:

    * a compound or descendant selector — ``.d-none.d-md-table-cell``,
      ``button[title] .visually-hidden`` — which styles a narrower case;
    * a class named inside a CSS comment. The shim in ``design-tokens.css``
      documents the component classes it deliberately does not provide, and
      writes them as a comma-separated list, so a naive scan reads
      ``.form-select-sm,`` as a selector and reports the gap closed.

    Comments are therefore stripped before matching.
    """
    css_text = _CSS_COMMENT.sub(" ", css_text)
    pattern = re.escape(selector) + r"\s*(?=[,{])"
    for match in re.finditer(pattern, css_text):
        start = match.start()
        # Reject a match that is the tail of a longer class or a descendant part.
        preceding = css_text[max(0, start - 1) : start]
        if preceding and (preceding.isalnum() or preceding in "-_."):
            continue
        # A descendant/compound rule ("x .visually-hidden{") does not define it.
        line_start = css_text.rfind("\n", 0, start) + 1
        prefix = css_text[line_start:start].strip()
        if prefix and not prefix.endswith(","):
            continue
        return True
    return False


class TenantAdminUtilityClassesTests(SimpleTestCase):
    """The classes tenant /admin/ markup depends on must actually be defined."""

    maxDiff = None

    def setUp(self):
        self.sheets = _tenant_reachable_stylesheets(_BASE_SITE)
        self.assertTrue(
            self.sheets, "parsed no stylesheets from base_site.html — parser is broken"
        )

    def _tenant_css(self) -> str:
        chunks = []
        for rel in self.sheets:
            path = Path("static") / rel
            if path.exists():
                chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
        return "\n".join(chunks)

    def test_bootstrap_itself_is_not_reachable_on_tenant_admin(self):
        """Guards the premise: if Bootstrap ever loads for tenants, relax the rest."""
        self.assertNotIn(
            "vendor/bootstrap/css/bootstrap.min.css",
            self.sheets,
            "premise changed — tenant /admin/ now loads Bootstrap, so revisit this module",
        )

    def test_visually_hidden_is_defined_for_tenant_admin(self):
        self.assertTrue(
            _defines(self._tenant_css(), ".visually-hidden"),
            "tenant /admin/ never defines .visually-hidden, so every element relying on "
            "it to be invisible renders as a visible block and reserves layout space",
        )

    def test_d_none_is_defined_for_tenant_admin(self):
        self.assertTrue(
            _defines(self._tenant_css(), ".d-none"),
            "tenant /admin/ never defines .d-none, so the campus switcher shows a "
            "permanent 'Loading schools…' placeholder that JS is never asked to clear",
        )

    def test_layout_primitives_are_defined_for_tenant_admin(self):
        """Flex/position/spacing utilities shared components use unconditionally.

        These are not cosmetic. With ``.position-absolute`` undefined an overlay
        panel joins the normal flow and pushes the page down; with
        ``.flex-column`` undefined a column lays out as a row. Component-level
        Bootstrap classes are deliberately excluded — they need their component
        bundle, not a utility shim.
        """
        css = self._tenant_css()
        primitives = [
            ".align-items-center",
            ".flex-column",
            ".flex-grow-1",
            ".d-inline",
            ".d-inline-flex",
            ".position-absolute",
            ".position-relative",
            ".start-0",
            ".top-100",
            ".ms-auto",
            ".ms-2",
            ".me-1",
            ".me-2",
            ".text-decoration-none",
            ".fw-semibold",
        ]
        undefined = [name for name in primitives if not _defines(css, name)]
        self.assertEqual(
            undefined,
            [],
            f"tenant /admin/ uses these layout utilities with nothing to honour them: {undefined}",
        )

    def test_shim_is_not_satisfied_by_a_comment(self):
        """A class NAMED in a CSS comment is not a definition.

        The shim's own comment lists the component classes it deliberately skips.
        A checker that reads comments would count those as provided and report a
        clean surface that isn't — so the definition test must ignore comments.
        """
        commented_only = (
            "/* deliberately not shimmed: .form-select-sm, .dropdown-menu-end, "
            ".modal-dialog-centered */\n.something-else { color: red; }"
        )
        self.assertFalse(
            _defines(commented_only, ".form-select-sm"),
            "a class listed in a comment — comma and all — was treated as defined, "
            "which would report the tenant surface clean while the gap is still open",
        )
        self.assertTrue(
            _defines(commented_only, ".something-else"),
            "stripping comments must not swallow real rules",
        )

    def test_operator_admin_still_gets_bootstrap(self):
        """The fix must not be achieved by taking Bootstrap away from the operator."""
        source = _BASE_SITE.read_text(encoding="utf-8")
        self.assertIn(
            "vendor/bootstrap/css/bootstrap.min.css",
            source,
            "operator /admin/ lost its Bootstrap link",
        )


class TenantAdminMarkupDependsOnThoseClassesTests(SimpleTestCase):
    """Proof the classes above are load-bearing, not incidental."""

    def test_admin_base_opens_with_a_visually_hidden_sentinel(self):
        source = _ADMIN_BASE.read_text(encoding="utf-8")
        self.assertIn(
            "visually-hidden rmc-empty-state-sentinel",
            source,
            "the sentinel this module is about is gone — re-check the premise",
        )

    def test_campus_switcher_starts_hidden_behind_d_none(self):
        source = _UTILITIES.read_text(encoding="utf-8")
        self.assertIn(
            'class="rmc-campus-switcher d-none"',
            source,
            "campus switcher no longer starts hidden — re-check the premise",
        )
        self.assertIn(
            "Loading schools",
            source,
            "the placeholder this module is about is gone — re-check the premise",
        )
