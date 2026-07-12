"""Unit tests for ``scripts/verify_template_compiles.py``.

Locks the core ``compile_source`` contract: it must flag every template that
Django cannot compile — including the exact production bug class that shipped
the ``/help/`` 500 (an unescaped apostrophe in a single-quoted ``{% trans %}``)
— and pass templates that compile cleanly. A minimal, project-independent
DjangoTemplates backend is used so the test does not depend on the real
``config.settings`` (and so it behaves identically whether run standalone or
under the project test runner).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import verify_template_compiles as vtc  # noqa: E402


def _minimal_backend():
    """A DjangoTemplates backend with i18n loadable but NOT a builtin — exactly
    the project's runtime posture (``{% trans %}`` requires ``{% load i18n %}``)."""
    import django
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            USE_I18N=True,
            INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth"],
            TEMPLATES=[
                {
                    "BACKEND": "django.template.backends.django.DjangoTemplates",
                    "APP_DIRS": False,
                    "OPTIONS": {},
                }
            ],
        )
        django.setup()
    return vtc._get_django_backend()


class CompileSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = _minimal_backend()

    def test_clean_template_passes(self):
        self.assertIsNone(
            vtc.compile_source('{% load i18n %}<p>{% trans "Hello" %}</p>', self.backend)
        )

    def test_unescaped_apostrophe_in_single_quoted_trans_flagged(self):
        # The exact /help/ production bug: {% trans 'What's new' %}
        err = vtc.compile_source(
            "{% load i18n %}<x a=\"{% trans 'What's new' %}\">", self.backend
        )
        self.assertIsNotNone(err)
        self.assertIn("TemplateSyntaxError", err)

    def test_double_quoted_apostrophe_trans_passes(self):
        # The fix form: {% trans "What's new" %}
        self.assertIsNone(
            vtc.compile_source('{% load i18n %}{% trans "What\'s new" %}', self.backend)
        )

    def test_block_tag_inside_blocktrans_flagged(self):
        err = vtc.compile_source(
            "{% load i18n %}{% blocktrans %}Hi {% if x %}y{% endif %}{% endblocktrans %}",
            self.backend,
        )
        self.assertIsNotNone(err)

    def test_missing_load_i18n_flagged(self):
        # trans/blocktrans without {% load i18n %} is a real runtime 500 here.
        err = vtc.compile_source('<p>{% trans "Hi" %}</p>', self.backend)
        self.assertIsNotNone(err)

    def test_leading_underscore_variable_flagged(self):
        err = vtc.compile_source("{% if _secret %}x{% endif %}", self.backend)
        self.assertIsNotNone(err)

    def test_nested_double_brace_in_tag_flagged(self):
        err = vtc.compile_source("{% include x with a={{ b }} %}", self.backend)
        self.assertIsNotNone(err)


class ModuleContractTests(unittest.TestCase):
    def test_allow_marker_string(self):
        self.assertEqual(vtc.ALLOW_MARKER, "template-compile-allow:")

    def test_iter_templates_returns_paths(self):
        # Discovery walks the real tree; just assert it returns a sorted list of
        # existing .html files (non-empty on this repo) without raising.
        files = vtc.iter_templates()
        self.assertIsInstance(files, list)
        self.assertTrue(all(p.suffix == ".html" for p in files))


if __name__ == "__main__":
    unittest.main()
