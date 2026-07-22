"""Regression: ops center frame must not 500 when ops_surface is absent.

Production 2026-07-22: /super/schools/ and /configuration/ raised
VariableDoesNotExist for ops_surface inside
``{% include … with page_host=page_host|default:ops_surface|… %}``.

Django resolves every ``|default:`` / ``|default_if_none:`` *argument*
eagerly — even when the left-hand value is already set. Literal defaults only.
"""

from __future__ import annotations

from django.template import Context, Template
from django.template.base import VariableDoesNotExist
from django.test import SimpleTestCase


class OperationalCenterFrameIncludeTests(SimpleTestCase):
    def test_frame_renders_without_ops_surface_or_ops_page_archetype(self):
        tpl = Template(
            "{% include 'components/rmc_operational_center_frame.html' "
            "with os_center_key='schools_list' "
            "center_eyebrow='Platform operators' "
            "center_title='Schools' "
            "center_purpose='' "
            "primary_url='' "
            "primary_label='' "
            "nav_groups=nav_groups %}"
        )
        html = tpl.render(
            Context(
                {
                    "nav_groups": [
                        {
                            "key": "fleet",
                            "label": "Fleet",
                            "title": "Fleet",
                            "body": "Schools",
                        }
                    ],
                }
            )
        )
        self.assertIn("rmc-operational-center-frame", html)
        self.assertIn("Schools", html)

    def test_frame_tenant_branch_without_ops_page_archetype(self):
        tpl = Template(
            "{% include 'components/rmc_operational_center_frame.html' "
            "with tenant_surface='1' "
            "os_center_key='tenant_pack_setup' "
            "center_eyebrow='Setup' "
            "center_title='Packs' "
            "center_purpose='' "
            "nav_groups=nav_groups %}"
        )
        html = tpl.render(Context({"nav_groups": []}))
        self.assertIn("rmc-operational-center-frame--tenant", html)

    def test_default_filter_arg_raises_even_when_left_hand_is_set(self):
        """Seal: Django 5.2 eagerly resolves |default: args (not short-circuit)."""
        tpl = Template("{{ a|default:missing_fallback }}")
        with self.assertRaises(VariableDoesNotExist):
            tpl.render(Context({"a": "present"}))

    def test_literal_default_is_safe_when_fallback_context_absent(self):
        tpl = Template('{{ a|default:"literal-ok" }}')
        self.assertEqual(tpl.render(Context({})), "literal-ok")
