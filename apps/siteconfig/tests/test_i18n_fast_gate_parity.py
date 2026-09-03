"""`verify_i18n_catalog_fresh_fast` must answer exactly what the slow gate answers.

The fast gate is 15x cheaper (170.5s -> 11.0s measured 2026-08-31) for one reason:
it refuses to look at files that cannot possibly contain a translatable string, and
it reads the ``en`` catalog's msgids without polib. Both shortcuts are only
legitimate while they are LOSSLESS, and both fail in the same silent direction --
a missed string is a green gate, which is the exact failure this repository keeps
finding in its own detectors.

So the two shortcuts are tested directly, against a synthetic tree that exercises
every extractor pattern the builder supports plus the cases the prefilter could get
wrong:

* the byte prefilter (``_(`` / ``gettext`` / ``trans``) vs the full walk, and
* the stdlib msgid scan vs ``polib`` on the REAL 20k-entry ``en`` catalog.

These run the extractors and compare their OUTPUT. Nothing here asserts that a word
appears in a file.
"""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

REPO_ROOT = Path(settings.BASE_DIR)


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FAST = _load("_fast_i18n_gate", "scripts/verify_i18n_catalog_fresh_fast.py")
BUILDER = _load("_i18n_builder_under_test", "apps/siteconfig/i18n_catalog_builder.py")


#: One file per extractor pattern, plus the shapes the prefilter could drop.
FIXTURE_TREE: dict[str, str] = {
    "templates/a_trans_double.html": '{% load i18n %}{% trans "TD double quoted" %}',
    "templates/b_trans_single.html": "{% load i18n %}{% trans 'TS single quoted' %}",
    "templates/c_blocktrans.html": (
        "{% load i18n %}{% blocktrans %}BT wrapped body{% endblocktrans %}"
    ),
    "templates/d_var_underscore.html": '{{ _("VU underscore call") }}',
    "templates/e_plain.txt": '{% trans "PT text template" %}',
    # No needle at all -> the prefilter skips it, and it must genuinely yield nothing.
    "templates/f_no_needle.html": "<p>plain markup, nothing translatable</p>",
    "apps/gateproofapp/models.py": (
        "from django.utils.translation import gettext_lazy as _\n"
        'NAME = _("PY gettext_lazy call")\n'
    ),
    "apps/gateproofapp/views.py": (
        "from django.utils.translation import gettext, ngettext, pgettext\n"
        'A = gettext("PY gettext call")\n'
        'B = ngettext("PY ngettext one", "PY ngettext many", 2)\n'
        'C = pgettext("ctx", "PY pgettext call")\n'
    ),
    # A test module: the builder skips these on purpose, so the fast path must too.
    "apps/gateproofapp/tests/test_thing.py": (
        "from django.utils.translation import gettext as _\n"
        'SKIPPED = _("PY inside a tests package")\n'
    ),
    "apps/gateproofapp/templates/gateproofapp/g.html": (
        '{% load i18n %}{% trans "APP template string" %}'
    ),
    "config/settings_probe.py": (
        "from django.utils.translation import gettext_lazy as _\n"
        'CONF = _("CONFIG module string")\n'
    ),
    "services/probe.py": (
        "from django.utils.translation import gettext_lazy as _\n"
        'SVC = _("SERVICES module string")\n'
    ),
    "static/js/probe.js": 'const t = gettext("JS gettext string");',
    "static/js/quiet.js": "const t = 1;",
}


class ExtractorParityTests(SimpleTestCase):
    """The prefiltered walk must find exactly what the full walk finds."""

    def setUp(self):
        self.tree = Path(tempfile.mkdtemp(prefix="rmc_i18n_parity_"))
        self.addCleanup(shutil.rmtree, self.tree, True)
        for relative, body in FIXTURE_TREE.items():
            path = self.tree / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")

    def test_fast_and_slow_extractors_agree_on_a_synthetic_tree(self):
        slow = BUILDER.collect_translatable_strings(self.tree)
        fast = FAST.collect_translatable_strings_fast(self.tree, BUILDER)
        self.assertEqual(
            fast,
            slow,
            "the byte prefilter dropped a string the full walk found: "
            f"{sorted(slow - fast)}",
        )

    def test_the_fixture_actually_exercises_every_pattern(self):
        """A parity test over an empty result set would prove nothing."""
        found = BUILDER.collect_translatable_strings(self.tree)
        for expected in (
            "TD double quoted",
            "TS single quoted",
            "BT wrapped body",
            "VU underscore call",
            "PT text template",
            "PY gettext_lazy call",
            "PY gettext call",
            "PY ngettext one",
            "PY pgettext call",
            "APP template string",
            "CONFIG module string",
            "SERVICES module string",
            "JS gettext string",
        ):
            with self.subTest(msgid=expected):
                self.assertIn(expected, found)
        self.assertNotIn("PY inside a tests package", found)


class MsgidScanParityTests(SimpleTestCase):
    """The stdlib msgid scan must agree with polib on the catalog that ships."""

    def test_stdlib_scan_matches_polib_on_the_real_en_catalog(self):
        import polib

        po_path = REPO_ROOT / "locale" / "en" / "LC_MESSAGES" / "django.po"
        self.assertTrue(po_path.is_file())
        from_polib = {e.msgid for e in polib.pofile(str(po_path)) if e.msgid}
        from_scan = FAST.po_msgids(po_path)
        self.assertEqual(
            from_scan,
            from_polib,
            "msgid scan disagreed with polib: "
            f"only-polib={sorted(from_polib - from_scan)[:5]} "
            f"only-scan={sorted(from_scan - from_polib)[:5]}",
        )
        self.assertGreater(len(from_scan), 10000, "the catalog should be large")


class DriftDetectionTests(SimpleTestCase):
    """The gate must go red on a string that is wrapped but never extracted."""

    def setUp(self):
        self.tree = Path(tempfile.mkdtemp(prefix="rmc_i18n_drift_"))
        self.addCleanup(shutil.rmtree, self.tree, True)
        catalog = self.tree / "locale" / "en" / "LC_MESSAGES"
        catalog.mkdir(parents=True)
        (catalog / "django.po").write_text(
            'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
            'msgid "Already extracted"\nmsgstr "Already extracted"\n',
            encoding="utf-8",
        )
        (self.tree / "templates").mkdir()
        (self.tree / "templates" / "ok.html").write_text(
            '{% load i18n %}{% trans "Already extracted" %}', encoding="utf-8"
        )

    def test_clean_tree_reports_no_missing_msgids(self):
        self.assertEqual(FAST.missing_msgids(self.tree, BUILDER), set())

    def test_a_wrapped_but_unextracted_string_is_reported(self):
        (self.tree / "templates" / "drift.html").write_text(
            '{% load i18n %}{% trans "Newly wrapped and never synced" %}',
            encoding="utf-8",
        )
        self.assertEqual(
            FAST.missing_msgids(self.tree, BUILDER),
            {"Newly wrapped and never synced"},
        )

    def test_gate_exits_nonzero_on_drift(self):
        (self.tree / "templates" / "drift.html").write_text(
            '{% load i18n %}{% trans "Newly wrapped and never synced" %}',
            encoding="utf-8",
        )
        baseline = self.tree / "baseline.json"
        baseline.write_text('{"finding_count": 0, "missing": []}', encoding="utf-8")
        rc = FAST.main(
            ["--base", str(self.tree), "--baseline", str(baseline), "--compare", "--quiet"]
        )
        self.assertEqual(rc, 1)

    def test_a_baselined_gap_does_not_fail_compare(self):
        (self.tree / "templates" / "drift.html").write_text(
            '{% load i18n %}{% trans "Newly wrapped and never synced" %}',
            encoding="utf-8",
        )
        baseline = self.tree / "baseline.json"
        baseline.write_text(
            '{"finding_count": 1, "missing": ["Newly wrapped and never synced"]}',
            encoding="utf-8",
        )
        rc = FAST.main(
            ["--base", str(self.tree), "--baseline", str(baseline), "--compare", "--quiet"]
        )
        self.assertEqual(rc, 0)
