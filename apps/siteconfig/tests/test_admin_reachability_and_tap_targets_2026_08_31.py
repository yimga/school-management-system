"""Two invariants that each silently produced a surface nobody could use.

1. NO REPO-OWNED ADMIN ON THE DEFAULT SITE.
   ``django.contrib.admin.site`` is mounted by no urlconf in this repo --
   config/urls.py, tenant_urls.py, manager_urls.py and public_urls.py were all
   read. A bare ``@admin.register(Model)`` or ``admin.site.register(Model)``
   therefore builds a screen that no host can open. Seventeen of them had
   accumulated across five apps, plus an entire never-imported module.

   Third-party packages register themselves on that site from their own code
   (django_celery_beat, django_otp, simplejwt's token_blacklist). We do not own
   those, so the assertion is scoped to admins defined under ``apps.``.

2. THE INFO GLYPH'S TEXT-SHIELD EXEMPTION MUST STAY IN SYNC.
   ``.rmc-info-tag__btn`` is an icon-only button. The text-shield clamp
   (``overflow:hidden; text-overflow:ellipsis; white-space:nowrap``) has nothing
   to ellipsize on it and only served to CLIP the invisible 24x24 touch region
   that rmc-class-grammar.css gives it -- measured with CDP elementFromPoint,
   which hit the <h1> rather than the button at all four corners.

   The exemption has to exist in TWO places that share one selector: the CSS
   rule in rmc-isomorphic-grid-sweep.css, and the JS marker in
   rmc-isomorphic-grid-sweep.js that stamps ``data-rmc-text-shield="1"``.
   Fixing only the CSS leaves the JS stamping the attribute, and the attribute
   selector re-applies overflow:hidden -- which is exactly what happened on the
   first attempt. Pin both so an edit to one cannot silently undo the other.
"""

from __future__ import annotations

import ast
import pathlib
import re

from django.contrib import admin as django_admin
from django.test import SimpleTestCase

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SWEEP_CSS = REPO_ROOT / "static" / "css" / "rmc-isomorphic-grid-sweep.css"
SWEEP_JS = REPO_ROOT / "static" / "js" / "rmc-isomorphic-grid-sweep.js"
GRAMMAR_CSS = REPO_ROOT / "static" / "css" / "rmc-class-grammar.css"

URLCONFS = ("urls", "tenant_urls", "manager_urls", "public_urls")

# The shielded-button selector, shared by the stylesheet and the runtime.
SHIELD_BTN = re.compile(
    r"\.btn:not\(\.rmc-btn-wrap\):not\(\.btn-link\):not\(\.dropdown-toggle\)"
    r"(?P<exempt>:not\(\.rmc-info-tag__btn\))?"
)


def _attr_path(node) -> str:
    """Dotted name for an ast expression, e.g. 'admin.site.register'."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def bare_registrations(source: str) -> list[tuple[int, str]]:
    """(lineno, description) for every registration naming no admin site.

    AST rather than a regex on purpose: the first attempt matched
    ``@admin.register(Model)`` inside the very comments that explain this fix,
    and inside docstrings quoting the old code. A parser cannot see either.
    """
    found: list[tuple[int, str]] = []
    tree = ast.parse(source)

    for node in ast.walk(tree):
        # @admin.register(Thing)  -- with no site= keyword
        for dec in getattr(node, "decorator_list", []) or []:
            if not isinstance(dec, ast.Call):
                continue
            if _attr_path(dec.func) != "admin.register":
                continue
            if any(kw.arg == "site" for kw in dec.keywords):
                continue
            model = dec.args[0].id if dec.args and isinstance(dec.args[0], ast.Name) else "?"
            found.append((dec.lineno, f"@admin.register({model})"))
        # admin.site.register(Thing)
        if isinstance(node, ast.Call) and _attr_path(node.func) == "admin.site.register":
            model = node.args[0].id if node.args and isinstance(node.args[0], ast.Name) else "?"
            found.append((node.lineno, f"admin.site.register({model})"))
    return sorted(set(found))


class NoRepoAdminOnTheUnmountedDefaultSiteTests(SimpleTestCase):
    def test_no_urlconf_mounts_the_default_admin_site(self) -> None:
        """The premise. If this ever changes, the test below is moot."""
        mounted = []
        for name in URLCONFS:
            path = REPO_ROOT / "config" / f"{name}.py"
            if not path.exists():
                continue
            src = path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"\badmin\.site\.urls\b", src):
                mounted.append(name)
        self.assertEqual(
            mounted,
            [],
            f"config/{mounted} now mounts Django's default admin.site. That is a "
            "deliberate architecture change, not a slip -- but it makes "
            "test_no_repo_model_admin_lands_on_it below meaningless, so revisit "
            "both together.",
        )

    def test_no_repo_model_admin_lands_on_it(self) -> None:
        offenders = []
        for model, model_admin in django_admin.site._registry.items():
            defining = type(model_admin).__module__ or ""
            if not defining.startswith("apps."):
                # Third-party package registering itself; not ours to move.
                continue
            offenders.append(
                f"{model._meta.label} ({type(model_admin).__name__} in "
                f"{defining}) is on the default admin.site, which no urlconf "
                "mounts -- pass site=tenant_admin_site / site=platform_admin_site, "
                "or use register_tenant_admin / register_platform_admin / "
                "register_both"
            )
        self.assertEqual(sorted(offenders), [])

    def test_no_admin_source_file_carries_a_bare_registration(self) -> None:
        """The live registry cannot see a module that never imports.

        ``apps/portal/admin_kb.py`` is imported by nothing, so its eight bare
        ``@admin.register(Model)`` calls never executed and never appeared in
        ``admin.site._registry`` -- which is exactly why they sat unnoticed. The
        runtime assertion above is therefore blind to them by construction, and
        this static pass covers that half.
        """
        offenders = []
        for path in sorted((REPO_ROOT / "apps").rglob("admin*.py")):
            if "/tests/" in path.as_posix() or "/migrations/" in path.as_posix():
                continue
            src = path.read_text(encoding="utf-8", errors="ignore")
            rel = path.relative_to(REPO_ROOT).as_posix()
            try:
                hits = bare_registrations(src)
            except SyntaxError as exc:  # pragma: no cover - unparsable admin
                offenders.append(f"{rel} does not parse: {exc}")
                continue
            offenders.extend(f"{rel}:{line} {what}" for line, what in hits)
        self.assertEqual(
            sorted(offenders),
            [],
            "these name no admin site, so they target Django's default "
            "admin.site, which no urlconf mounts. Pass site=... or use "
            "register_tenant_admin / register_platform_admin / register_both.",
        )

    def test_the_readers_actually_discriminate(self) -> None:
        """Every assertion here passes by finding nothing; so would a broken one."""

        class FakeAdmin:
            pass

        FakeAdmin.__module__ = "apps.somewhere.admin"
        self.assertTrue(FakeAdmin.__module__.startswith("apps."))
        FakeAdmin.__module__ = "django_celery_beat.admin"
        self.assertFalse(FakeAdmin.__module__.startswith("apps."))

        # the urlconf reader finds a mount when there is one
        self.assertIsNotNone(re.search(r"\badmin\.site\.urls\b", "path('a/', admin.site.urls)"))
        self.assertIsNone(re.search(r"\badmin\.site\.urls\b", "path('a/', tenant_admin_site.urls)"))

        # the static reader flags a bare decorator and a default-site call, and
        # leaves a properly targeted registration alone
        bare = "@admin.register(Thing)\nclass A:\n    pass\n"
        sited = "@admin.register(Thing, site=tenant_admin_site)\nclass A:\n    pass\n"
        self.assertEqual(
            [w for _, w in bare_registrations(bare)], ["@admin.register(Thing)"]
        )
        self.assertEqual(bare_registrations(sited), [])
        self.assertEqual(
            [w for _, w in bare_registrations("admin.site.register(Thing)\n")],
            ["admin.site.register(Thing)"],
        )
        self.assertEqual(bare_registrations("tenant_admin_site.register(Thing)\n"), [])
        # A comment or docstring quoting the old code must NOT trip it. The
        # first version of this reader was a regex and flagged the very
        # docstrings written to explain this fix.
        self.assertEqual(
            bare_registrations('"""we removed @admin.register(Thing)."""\n'), []
        )


class InfoGlyphTextShieldExemptionTests(SimpleTestCase):
    def test_css_and_js_agree_on_the_exemption(self) -> None:
        css = SWEEP_CSS.read_text(encoding="utf-8", errors="ignore")
        js = SWEEP_JS.read_text(encoding="utf-8", errors="ignore")

        # The selector appears twice in the stylesheet: once on a min/max-width
        # rule (harmless, deliberately left alone) and once on the overflow
        # clamp. Keying off "the first rule that sets overflow:hidden" picks up
        # an unrelated earlier rule, so walk the OCCURRENCES of the selector and
        # look at the declaration block each one actually opens.
        clamped = []
        for m in SHIELD_BTN.finditer(css):
            end = css.find("}", m.end())
            block = css[m.end(): end if end != -1 else len(css)]
            if re.search(r"overflow:\s*hidden", block):
                clamped.append(m)

        self.assertTrue(
            clamped,
            "no .btn shield selector in rmc-isomorphic-grid-sweep.css opens a "
            "block that sets overflow:hidden -- the clamp was renamed or removed, "
            "so this guard is no longer watching anything.",
        )
        for m in clamped:
            self.assertIsNotNone(
                m.group("exempt"),
                "rmc-isomorphic-grid-sweep.css: every .btn shield selector that "
                "applies overflow:hidden must exempt :not(.rmc-info-tag__btn). "
                "That button is icon-only -- the clamp ellipsizes nothing on it "
                "and only clips its invisible 24x24 touch region.",
            )

        js_match = SHIELD_BTN.search(js)
        self.assertIsNotNone(
            js_match, "TEXT_SHIELD_SELECTOR no longer contains the .btn entry"
        )
        self.assertIsNotNone(
            js_match.group("exempt"),
            "rmc-isomorphic-grid-sweep.js: TEXT_SHIELD_SELECTOR must exempt "
            ":not(.rmc-info-tag__btn) too. Exempting only the CSS leaves this "
            'marker stamping data-rmc-text-shield="1", and the attribute '
            "selector re-applies overflow:hidden -- the button stays clipped.",
        )

    def test_the_touch_region_rule_is_present(self) -> None:
        grammar = GRAMMAR_CSS.read_text(encoding="utf-8", errors="ignore")
        self.assertIn(
            ".rmc-info-tag__btn::after",
            grammar,
            "the invisible hit-area pseudo element is gone; the glyph paints "
            "14px wide and is that small to hit on a phone",
        )
        block = grammar.split(".rmc-info-tag__btn::after", 1)[1][:400]
        for prop in ("position: absolute", "24px", "translate(-50%, -50%)"):
            self.assertIn(prop, block, f"hit-area rule lost {prop!r}")

    def test_the_selector_reader_discriminates(self) -> None:
        exempt = ".btn:not(.rmc-btn-wrap):not(.btn-link):not(.dropdown-toggle):not(.rmc-info-tag__btn)"
        plain = ".btn:not(.rmc-btn-wrap):not(.btn-link):not(.dropdown-toggle)"
        self.assertIsNotNone(SHIELD_BTN.search(exempt).group("exempt"))
        self.assertIsNone(SHIELD_BTN.search(plain).group("exempt"))
