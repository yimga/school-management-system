"""Stdlib unittest coverage for ``verify_cross_host_template_reverse`` (parse layer).

The runtime phase (walking live host resolvers + resolving CBV template_names)
needs Django and is exercised in CI's django-tests job + by the verifier's own
``--compare`` (and a negative test that reinjects the original connector 500 and
confirms it flags). These tests lock the pure parse layer — host-guard detection,
unguarded namespaced-url extraction, and the allow-marker — with no Django DB.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_cross_host_template_reverse as v  # noqa: E402


class HostGuardTests(unittest.TestCase):
    def test_host_guard_conditions(self):
        self.assertTrue(v._is_host_guard("shell == 'portal'"))
        self.assertTrue(v._is_host_guard("request.public_host_kind == 'manager'"))
        self.assertTrue(v._is_host_guard("is_manager_host"))
        self.assertTrue(v._is_host_guard("is_control_plane"))

    def test_non_host_conditions(self):
        self.assertFalse(v._is_host_guard("user.is_authenticated"))
        self.assertFalse(v._is_host_guard("connections"))
        self.assertFalse(v._is_host_guard(""))


class UnguardedRefTests(unittest.TestCase):
    def test_plain_unguarded_ref_detected(self):
        t = "<a href=\"{% url 'foo:bar' %}\">x</a>"
        self.assertEqual(v._unguarded_ns_refs(t), [(1, "foo", "bar")])

    def test_ref_inside_shell_guard_skipped(self):
        t = (
            "{% if shell == 'portal' %}{% url 'foo:bar' %}"
            "{% else %}{% url 'baz:qux' %}{% endif %}"
        )
        self.assertEqual(v._unguarded_ns_refs(t), [])

    def test_ref_inside_public_host_kind_guard_skipped(self):
        t = "{% if request.public_host_kind == 'manager' %}{% url 'foo:bar' %}{% endif %}"
        self.assertEqual(v._unguarded_ns_refs(t), [])

    def test_non_host_if_does_not_skip(self):
        t = "{% if user.is_authenticated %}{% url 'foo:bar' %}{% endif %}"
        self.assertEqual(v._unguarded_ns_refs(t), [(1, "foo", "bar")])

    def test_guard_pops_at_endif(self):
        # A ref AFTER the host guard closes is not guarded.
        t = "{% if shell == 'portal' %}x{% endif %}{% url 'foo:bar' %}"
        self.assertEqual(v._unguarded_ns_refs(t), [(1, "foo", "bar")])

    def test_allow_marker_same_line_skips(self):
        t = "{% url 'foo:bar' %} {# cross-host-reverse-allow: intentional #}"
        self.assertEqual(v._unguarded_ns_refs(t), [])

    def test_allow_marker_line_above_skips(self):
        t = "{# cross-host-reverse-allow: intentional #}\n{% url 'foo:bar' %}"
        self.assertEqual(v._unguarded_ns_refs(t), [])

    def test_non_namespaced_url_ignored(self):
        self.assertEqual(v._unguarded_ns_refs("{% url 'plainname' %}"), [])


if __name__ == "__main__":
    unittest.main()
