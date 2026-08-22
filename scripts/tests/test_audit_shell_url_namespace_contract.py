"""The guard tracker behind `scripts/audit_shell_url_namespace_contract.py`.

The gate reports a hard `{% url %}` in shell chrome that cannot reverse on a host the
shell renders on. Its whole usability rests on telling a REAL one from a tag that is
already inside `{% if request.public_host_kind == 'manager' %}` -- a first cut without
guard tracking reported 53 tags, 47 of which could never fire. These tests pin the
guard logic, because a regression there does not break the gate loudly: it either
buries six real findings in noise, or silently stops reporting them.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "audit_shell_url_namespace_contract.py"
_spec = importlib.util.spec_from_file_location("audit_shell_url_namespace_contract", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["audit_shell_url_namespace_contract"] = mod
_spec.loader.exec_module(mod)


class _TemplateFixture(unittest.TestCase):
    """Point the module's resolver at a temp dir so fixtures are real files."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        root = Path(self._dir.name)
        self._orig = mod._template_path
        mod._template_path = lambda name: (
            str(root / name) if (root / name).is_file() else None
        )
        self.addCleanup(lambda: setattr(mod, "_template_path", self._orig))
        self.root = root

    def write(self, name: str, body: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


class HardTagDetectionTests(_TemplateFixture):
    def test_bare_url_tag_is_hard(self):
        self.write("t.html", "<a href=\"{% url 'portal:x' %}\">go</a>")
        tags, _, _ = mod.scan("t.html")
        self.assertEqual([t["view_name"] for t in tags], ["portal:x"])
        self.assertFalse(tags[0]["guarded"])

    def test_as_var_form_is_not_reported_at_all(self):
        # Django assigns "" instead of raising, so this can never 500. It is the
        # sanctioned escape hatch and must not appear even as a guarded row.
        self.write("t.html", "{% url 'portal:x' as u %}{% if u %}<a href=\"{{ u }}\">go</a>{% endif %}")
        tags, _, _ = mod.scan("t.html")
        self.assertEqual(tags, [])

    def test_variable_view_name_is_skipped(self):
        # {% url connector_ns|add:':home' %} is not statically knowable.
        self.write("t.html", "{% url connector_ns|add:':connector-home' %}")
        tags, _, _ = mod.scan("t.html")
        self.assertEqual(tags, [])


class GuardTrackingTests(_TemplateFixture):
    def test_host_conditional_marks_tag_guarded(self):
        self.write(
            "t.html",
            "{% if request.public_host_kind == 'manager' %}"
            "{% url 'super:dashboard' %}{% endif %}",
        )
        tags, _, _ = mod.scan("t.html")
        self.assertTrue(tags[0]["guarded"])

    def test_else_branch_of_a_host_chain_is_also_guarded(self):
        # user_account_center_menu.html does exactly this: the manager arm reverses
        # super:, the else arm is the tenant one. Both are host-selected.
        self.write(
            "t.html",
            "{% if request.public_host_kind == 'manager' %}{% url 'super:dashboard' %}"
            "{% else %}{% url 'portal:home' %}{% endif %}",
        )
        tags, _, _ = mod.scan("t.html")
        self.assertEqual(len(tags), 2)
        self.assertTrue(all(t["guarded"] for t in tags))

    def test_non_host_condition_does_not_guard(self):
        # The copilot rail's real bug: role-guarded, never host-guarded.
        self.write(
            "t.html",
            "{% if role == 'TEACHER' %}{% url 'evals:teacher_dashboard' %}{% endif %}",
        )
        tags, _, _ = mod.scan("t.html")
        self.assertFalse(tags[0]["guarded"])

    def test_guard_closes_at_endif(self):
        self.write(
            "t.html",
            "{% if request.public_host_kind == 'manager' %}safe{% endif %}"
            "{% url 'portal:x' %}",
        )
        tags, _, _ = mod.scan("t.html")
        self.assertFalse(tags[0]["guarded"])

    def test_nested_if_inside_host_guard_stays_guarded(self):
        self.write(
            "t.html",
            "{% if request.public_host_kind != 'manager' %}{% if role %}"
            "{% url 'portal:x' %}{% endif %}{% endif %}",
        )
        tags, _, _ = mod.scan("t.html")
        self.assertTrue(tags[0]["guarded"])


class ClosurePropagationTests(_TemplateFixture):
    def test_guarded_include_protects_the_whole_subtree(self):
        # A partial that only ever renders under a host guard is safe no matter how
        # its own tags are written -- portal_base does this for the tenant nav.
        self.write(
            "shell.html",
            "{% if request.public_host_kind != 'manager' %}"
            "{% include 'nav.html' %}{% endif %}",
        )
        self.write("nav.html", "{% url 'portal:x' %}")
        reach, _ = mod.walk("shell.html")
        self.assertTrue(reach["shell.html"])
        self.assertFalse(reach["nav.html"], "guarded include should close the path")

    def test_unguarded_include_leaves_the_subtree_open(self):
        self.write("shell.html", "{% include 'chip.html' %}")
        self.write("chip.html", "{% url 'portal:x' %}")
        reach, _ = mod.walk("shell.html")
        self.assertTrue(reach["chip.html"])

    def test_one_unguarded_path_wins_over_a_guarded_one(self):
        # portal_base includes the copilot rail unguarded AND control_plane_skeleton
        # includes it too. A partial is only safe if EVERY path to it is guarded.
        self.write(
            "shell.html",
            "{% if request.public_host_kind == 'manager' %}{% include 'p.html' %}{% endif %}"
            "{% include 'p.html' %}",
        )
        self.write("p.html", "{% url 'portal:x' %}")
        reach, _ = mod.walk("shell.html")
        self.assertTrue(reach["p.html"])

    def test_variable_include_is_reported_not_silently_dropped(self):
        # {% include portal_footer_partial %}. Claiming coverage we do not have is
        # the exact failure this whole gate exists to prevent.
        self.write("shell.html", "{% include portal_footer_partial %}")
        _, unresolved = mod.walk("shell.html")
        self.assertTrue(any("portal_footer_partial" in u for u in unresolved))


class DefectClassificationTests(unittest.TestCase):
    def test_missing_namespace_is_named(self):
        self.assertIn("'portal'", mod._defect("portal:x", set(), set()))

    def test_mounted_namespace_missing_name(self):
        self.assertEqual(
            mod._defect("portal:x", {"portal"}, set()),
            "namespace mounted but name not reversible",
        )

    def test_reversible_name_is_clean(self):
        self.assertEqual(mod._defect("portal:x", {"portal"}, {"portal:x"}), "")

    def test_unnamespaced_name(self):
        self.assertEqual(mod._defect("manager_help_center", set(), set()), "name not reversible")
        self.assertEqual(mod._defect("home", set(), {"home"}), "")


class DeclaredShellsTests(unittest.TestCase):
    def test_developer_urlconf_is_never_a_host(self):
        # config.urls mounts everything, so including it could only mask findings --
        # and a box misrouted onto it is what hid this class in the first place.
        for urlconfs in mod.SHELL_HOSTS.values():
            self.assertNotIn("config.urls", urlconfs)

    def test_portal_base_is_declared_multi_host(self):
        self.assertIn("config.manager_urls", mod.SHELL_HOSTS["portal_base.html"])
        self.assertIn("config.tenant_urls", mod.SHELL_HOSTS["portal_base.html"])


if __name__ == "__main__":
    unittest.main()
