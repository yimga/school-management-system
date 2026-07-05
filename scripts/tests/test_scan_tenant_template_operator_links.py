"""Unit tests for scripts/scan_tenant_template_operator_links.py (stdlib, no Django)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import scan_tenant_template_operator_links as m  # noqa: E402


class ManagerConditionTest(unittest.TestCase):
    def test_canonical_guard(self):
        self.assertTrue(m._is_manager_condition("request.public_host_kind == 'manager'"))
        self.assertTrue(m._is_manager_condition("public_host_kind == 'manager' and not request.school"))

    def test_boolean_flag_guards(self):
        self.assertTrue(m._is_manager_condition("is_manager_host"))
        self.assertTrue(m._is_manager_condition("CONTROL_PLANE_SHELL"))

    def test_non_guard(self):
        self.assertFalse(m._is_manager_condition("public_site_url"))
        self.assertFalse(m._is_manager_condition("user.is_authenticated"))


class ExtendsTest(unittest.TestCase):
    def test_operator_base_detected(self):
        self.assertTrue(m._extends_operator_base('{% extends "control_plane_base.html" %}\n'))
        self.assertTrue(m._extends_operator_base('{% extends "control_plane_skeleton.html" %}'))

    def test_tenant_base_not_excluded(self):
        self.assertFalse(m._extends_operator_base('{% extends "portal_base.html" %}'))
        self.assertFalse(m._extends_operator_base('{% extends "base.html" %}'))


class ScanTextTest(unittest.TestCase):
    def test_unguarded_super_link_flagged(self):
        text = '<a href="{% url \'super:dashboard\' %}">op</a>'
        self.assertEqual(len(m._scan_text(text)), 1)

    def test_guarded_super_link_safe(self):
        text = (
            "{% if request.public_host_kind == 'manager' %}"
            "<a href=\"{% url 'super:dashboard' %}\">op</a>"
            "{% endif %}"
        )
        self.assertEqual(m._scan_text(text), [])

    def test_else_branch_of_guard_is_unsafe(self):
        text = (
            "{% if public_host_kind == 'manager' %}ok"
            "{% else %}<a href=\"{% url 'super:dashboard' %}\">leak</a>{% endif %}"
        )
        self.assertEqual(len(m._scan_text(text)), 1)

    def test_manager_url_name_flagged(self):
        self.assertEqual(len(m._scan_text("{% url 'manager_help_center' %}")), 1)

    def test_literal_super_href_flagged(self):
        self.assertEqual(len(m._scan_text('<a href="/super/x/">y</a>')), 1)

    def test_marker_excuses(self):
        text = '<a href="{% url \'super:dashboard\' %}">op</a>{# operator-link-allow: x #}'
        self.assertEqual(m._scan_text(text), [])


class LiveTreeInvariantTest(unittest.TestCase):
    def test_repo_tree_clean(self):
        self.assertEqual(m.scan(), [], "unexpected tenant-template-operator-links findings")


if __name__ == "__main__":
    unittest.main()
