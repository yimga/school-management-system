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


class FunctionViewTemplateExtractionTests(unittest.TestCase):
    """The function-view discovery layer that closes the CBV blind spot: a view
    that names its template as a literal in ``render(request, "x.html")`` (the
    class that shipped the /help/ + dsar cross-host 500s, invisible to the CBV
    ``template_name`` walk)."""

    def test_render_shortcut_literal_extracted(self):
        src = 'def view(request):\n    return render(request, "help/help_center.html", ctx)\n'
        self.assertEqual(v._fv_rendered_templates(src), {"help/help_center.html"})

    def test_template_response_literal_extracted(self):
        src = 'def view(request):\n    return TemplateResponse(request, "a/b.html")\n'
        self.assertEqual(v._fv_rendered_templates(src), {"a/b.html"})

    def test_template_name_kwarg_extracted(self):
        src = 'def view(request):\n    return render(request, template_name="c.html")\n'
        self.assertEqual(v._fv_rendered_templates(src), {"c.html"})

    def test_multiple_renders_all_extracted(self):
        src = (
            "def view(request):\n"
            '    if x:\n        return render(request, "one.html")\n'
            '    return render(request, "two.html")\n'
        )
        self.assertEqual(v._fv_rendered_templates(src), {"one.html", "two.html"})

    def test_non_request_first_arg_skipped(self):
        # A custom obj.render(self, ...) must not be misread as the Django shortcut.
        src = 'def m(self):\n    return self.render(self, "x.html")\n'
        self.assertEqual(v._fv_rendered_templates(src), set())

    def test_render_to_string_not_treated_as_page_render(self):
        src = 'def view(request):\n    body = render_to_string("email.html", ctx)\n'
        self.assertEqual(v._fv_rendered_templates(src), set())

    def test_non_html_and_non_literal_skipped(self):
        src = (
            "def view(request):\n"
            '    render(request, "report.txt")\n'
            "    render(request, template_var)\n"
        )
        self.assertEqual(v._fv_rendered_templates(src), set())

    def test_looks_like_template(self):
        self.assertTrue(v._looks_like_template("a/b.html"))
        self.assertTrue(v._looks_like_template("x.htm"))
        self.assertFalse(v._looks_like_template("no-extension"))
        self.assertFalse(v._looks_like_template("has space.html"))
        self.assertFalse(v._looks_like_template("x.txt"))


class TwoTierFindingTests(unittest.TestCase):
    """The sensitivity split. A CBV ``template_name`` maps to hosts exactly (a
    namespace absent on ANY host is a real conditional 500 — the connector-home
    class). A function-view-only template is looser (shared app-includes attribute
    a page to hosts it never serves), so only a namespace absent on EVERY host it
    renders on — a guaranteed 500, the /help/ + dsar class — is a finding."""

    def test_cbv_flags_missing_on_any_host(self):
        # connector-home class: rendered on 3 hosts, ns absent on 2.
        self.assertTrue(
            v._is_finding(True, {"config.manager_urls", "config.tenant_urls"},
                          {"config.urls", "config.manager_urls", "config.tenant_urls"})
        )

    def test_function_view_flags_only_when_missing_on_all_hosts(self):
        # /help/ + dsar class: tenant-only page reversing an operator namespace
        # absent on the tenant host (its only host) → guaranteed 500 → finding.
        self.assertTrue(
            v._is_finding(False, {"config.tenant_urls"}, {"config.tenant_urls"})
        )

    def test_function_view_suppresses_shared_include_fp(self):
        # accounts backend_dashboard.html attributed to all 4 hosts via the shared
        # apps.accounts.urls include, reversing a tenant ns absent only on the
        # marketing host — not runtime-reachable there → must NOT be a finding.
        self.assertFalse(
            v._is_finding(
                False,
                {"config.public_urls"},
                {"config.urls", "config.public_urls", "config.tenant_urls",
                 "config.manager_urls"},
            )
        )

    def test_no_missing_is_never_a_finding(self):
        self.assertFalse(v._is_finding(True, set(), {"config.tenant_urls"}))
        self.assertFalse(v._is_finding(False, set(), {"config.tenant_urls"}))



# --- closure walk (added with the extends/include expansion) -----------------
#
# The gate used to scan a root template's OWN source only, so a bare reverse
# INHERITED from a shared parent/partial was invisible. That is how the
# command-palette 500 shipped: the palette reverses kb: and siteconfig: (absent
# from config.public_urls) and base.html includes it on every authenticated page,
# but an include-only partial is never a CBV template_name.


class AsFormIsNotAFindingTests(unittest.TestCase):
    """`{% url ... as var %}` cannot raise -- URLNode re-raises only when asvar is
    None. Flagging it would penalise the idiom this gate wants authors to adopt."""

    def test_bare_tag_is_reported(self):
        self.assertEqual(
            [(1, "kb", "kb_home")],
            v._unguarded_ns_refs("""<a href="{% url 'kb:kb_home' %}">x</a>"""),
        )

    def test_as_capture_is_skipped(self):
        self.assertEqual([], v._unguarded_ns_refs("{% url 'kb:kb_home' as kb_url %}"))

    def test_as_capture_with_args_is_skipped(self):
        self.assertEqual(
            [], v._unguarded_ns_refs("{% url 'kb:kb_article' slug as article_url %}")
        )


class UnguardedChildrenTests(unittest.TestCase):
    def test_extends_and_include_are_collected(self):
        text = '{% extends "base.html" %}{% include "components/palette.html" %}'
        self.assertEqual(
            {"base.html", "components/palette.html"}, v._unguarded_children(text)
        )

    def test_include_with_context_is_collected(self):
        self.assertEqual(
            {"partials/x.html"},
            v._unguarded_children('{% include "partials/x.html" with a=b only %}'),
        )

    def test_host_guarded_include_does_not_propagate(self):
        text = '{% if is_manager_host %}{% include "partials/m.html" %}{% endif %}'
        self.assertEqual(set(), v._unguarded_children(text))

    def test_non_host_condition_still_propagates(self):
        """base.html includes the palette under is_authenticated -- not a host
        guard, and the palette really does render on every host."""
        text = (
            "{% if request.user.is_authenticated %}"
            '{% include "components/rmc_command_palette.html" %}{% endif %}'
        )
        self.assertEqual(
            {"components/rmc_command_palette.html"}, v._unguarded_children(text)
        )

    def test_non_literal_include_is_skipped(self):
        self.assertEqual(set(), v._unguarded_children("{% include some_var %}"))


class PropagationTerminatesTests(unittest.TestCase):
    def test_depth_cap_is_defined_and_sane(self):
        self.assertGreaterEqual(v._MAX_TEMPLATE_DEPTH, 4)

    def test_propagate_is_a_noop_without_readable_templates(self):
        """A cycle or unreadable template must not hang or raise."""
        host_map = {"nonexistent-template-xyz.html": {"config.urls"}}
        v._propagate_hosts(host_map)
        self.assertEqual({"config.urls"}, host_map["nonexistent-template-xyz.html"])


if __name__ == "__main__":
    unittest.main()
