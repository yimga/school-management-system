"""Stdlib unittest coverage for ``verify_settings_key_integrity`` (AST layer).

The runtime resolution phase needs Django (exercised in CI's django-tests job +
the verifier's own --compare). These tests lock the pure-AST collection layer —
which reads are recognized, the no-default rule for getattr, the UPPER_SNAKE +
read-context + django.conf-import gating, and the guard/marker excuses — with
no Django dependency.
"""

from __future__ import annotations

import ast
import pathlib
import sys
import textwrap
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_settings_key_integrity as v  # noqa: E402

_IMP = "from django.conf import settings\n"


def _names(body: str):
    return v.collect_names(_IMP + textwrap.dedent(body))


class CollectionTests(unittest.TestCase):
    def test_collects_settings_attr(self):
        self.assertEqual([n for _, n in _names("x = settings.FEATURE_BUDGET_CAP")],
                         ["FEATURE_BUDGET_CAP"])

    def test_collects_getattr_without_default(self):
        self.assertEqual([n for _, n in _names('y = getattr(settings, "MY_KEY")')], ["MY_KEY"])

    def test_getattr_with_default_is_safe(self):
        self.assertEqual(_names('y = getattr(settings, "MY_KEY", None)'), [])

    def test_lowercase_attr_ignored(self):
        # settings.configure / settings.foo are not settings keys
        self.assertEqual(_names("settings.configure()\nz = settings.foo_bar"), [])

    def test_assignment_target_ignored(self):
        # settings.FOO = 1 (test/override style) is a write, not a read
        self.assertEqual(_names("settings.OVERRIDE_ME = 1"), [])

    def test_requires_django_conf_import(self):
        # same access, but no `from django.conf import settings` -> not ours
        src = textwrap.dedent("settings = object()\nx = settings.FOO_BAR")
        self.assertEqual(v.collect_names(src), [])

    def test_short_name_ignored(self):
        # needs 3+ chars of UPPER_SNAKE; settings.DB would be borderline-noise
        self.assertEqual(_names("x = settings.AB"), [])


class HasattrGuardTests(unittest.TestCase):
    def test_same_line_hasattr_guard_excused(self):
        self.assertTrue(v._hasattr_guarded(
            'x = settings.SITE_SETTINGS if hasattr(settings, "SITE_SETTINGS") else None',
            "SITE_SETTINGS"))
        self.assertTrue(v._hasattr_guarded(
            "x = settings.FOO if hasattr(settings, 'FOO') else 1", "FOO"))

    def test_unrelated_or_absent_hasattr_not_excused(self):
        self.assertFalse(v._hasattr_guarded("x = settings.FOO", "FOO"))
        self.assertFalse(v._hasattr_guarded(
            'x = settings.FOO if hasattr(settings, "BAR") else None', "FOO"))


class GuardMarkerTests(unittest.TestCase):
    def test_alias_tuple_detects_attributeerror(self):
        tree = ast.parse("_SOFT = (AttributeError, KeyError)\n_NO = (KeyError, ValueError)\n")
        aliases = v._exception_tuple_aliases(tree)
        self.assertIn("_SOFT", aliases)
        self.assertNotIn("_NO", aliases)

    def test_guard_attributeerror_and_named_tuple_and_negative(self):
        tree = ast.parse(
            textwrap.dedent(
                """
                _SOFT = (AttributeError, ValueError)
                try:
                    a = settings.A_KEY
                except AttributeError:
                    a = None
                try:
                    b = settings.B_KEY
                except _SOFT:
                    b = None
                try:
                    c = settings.C_KEY
                except ValueError:
                    c = None
                """
            )
        )
        guarded = v._guarded_linenos(tree)
        self.assertIn(4, guarded)       # AttributeError-guarded
        self.assertIn(8, guarded)       # named-tuple-guarded
        self.assertNotIn(12, guarded)   # ValueError-only -> not guarded

    def test_marker_excuses_same_and_above(self):
        marked = v._marked_linenos(
            [
                "x = settings.A  # settings-key-allow: env-conditional",  # 1
                "# settings-key-allow: above",  # 2
                "y = settings.B",  # 3
            ]
        )
        self.assertTrue(v._is_excused(1, set(), marked))
        self.assertTrue(v._is_excused(3, set(), marked))
        self.assertFalse(v._is_excused(9, set(), marked))


if __name__ == "__main__":
    unittest.main()
