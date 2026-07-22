"""Regression: ops center frame must not 500 when ops_surface is absent.

Production 2026-07-22: /super/schools/ and /configuration/ raised
VariableDoesNotExist for ops_surface inside
``{% include … with page_host=page_host|default:ops_surface|… %}``.
"""

from __future__ import annotations

from django.template import Context, Template
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
