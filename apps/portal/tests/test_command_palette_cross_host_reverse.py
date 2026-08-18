"""The global command palette must survive a urlconf that does not mount every namespace.

``base.html`` includes ``components/rmc_command_palette.html`` for EVERY authenticated
request. But namespaces are NOT uniform across the host urlconfs: ``kb`` and
``siteconfig`` are mounted on ``config/urls.py``, ``config/tenant_urls.py`` and
``config/manager_urls.py`` -- and absent from ``config/public_urls.py``, which serves
the base/verify/support hosts and any unknown school subdomain.

Two bare tags in the palette (``kb:kb_home`` and ``siteconfig:ai_center``) therefore
turned the branded "school not found" page into a 500 for signed-in visitors: a parent
mistyping their school's subdomain got a hard error instead of the finder. Either tag
alone was sufficient to break the page. Most neighbouring entries already used the
guarded ``{% url ... as var %}`` + ``{% if var %}`` idiom; these did not.

Sibling of ``apps/accounts/tests/test_cross_host_admin_reverse.py`` -- same root cause
(reversing a namespace the ACTIVE urlconf does not mount), different namespaces.
``verify_cross_host_template_reverse`` does not catch it: that gate resolves template
``{% url %}`` names against the UNION of all hosts, so a name mounted on any one host
looks reachable from every host.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.template.loader import get_template
from django.test import SimpleTestCase, override_settings
from django.urls import NoReverseMatch, reverse

PALETTE = "components/rmc_command_palette.html"

#: Every urlconf a real request can be routed to (apps/schools/middleware.py picks
#: between them by host; PUBLIC_SCHEMA_URLCONF pins the public schema to public_urls).
HOST_URLCONFS = (
    "config.urls",
    "config.tenant_urls",
    "config.public_urls",
    "config.manager_urls",
)

#: `{% url 'ns:name' %}` / `{% url "ns:name" %}` with no `as` capture.
_BARE_URL_TAG = re.compile(r"\{%\s*url\s+['\"]([a-zA-Z0-9_:]+)['\"](?![^%]*\bas\b)")


def _palette_source() -> str:
    return Path(get_template(PALETTE).origin.name).read_text(encoding="utf8")


class PaletteRendersOnEveryHostTests(SimpleTestCase):
    """The behavioural contract: platform-wide means every host, not most hosts."""

    def test_palette_renders_under_each_host_urlconf(self):
        for urlconf in HOST_URLCONFS:
            with self.subTest(urlconf=urlconf):
                with override_settings(ROOT_URLCONF=urlconf):
                    try:
                        get_template(PALETTE).render({})
                    except NoReverseMatch as exc:
                        self.fail(
                            f"command palette raised NoReverseMatch under {urlconf}: "
                            f"{exc}. base.html includes this palette on every "
                            "authenticated page, so this 500s the whole host. Guard it: "
                            "{% url 'ns:name' as var %}{% if var %}...{% endif %}"
                        )


class PaletteBareReversesAreHostSafeTests(SimpleTestCase):
    """A bare tag is fine ONLY for a name every host can reverse."""

    def test_every_bare_reverse_resolves_on_every_host(self):
        offenders: list[str] = []
        for name in sorted(set(_BARE_URL_TAG.findall(_palette_source()))):
            missing = []
            for urlconf in HOST_URLCONFS:
                try:
                    reverse(name, urlconf=urlconf)
                except NoReverseMatch:
                    missing.append(urlconf)
                except Exception:  # noqa: BLE001 - needs args/kwargs, not a host gap
                    break
            if missing:
                offenders.append(f"{name} unreachable on {', '.join(missing)}")
        self.assertEqual(
            offenders,
            [],
            "Bare reverse(s) in the platform-wide palette that some host cannot "
            "resolve; use {% url ... as var %} + {% if var %}.",
        )


class KbAndSiteconfigAsymmetryTests(SimpleTestCase):
    """Pin the asymmetry that made the guards load-bearing."""

    def test_public_urls_lacks_kb_and_siteconfig(self):
        for name in ("kb:kb_home", "siteconfig:ai_center"):
            with self.subTest(name=name):
                reverse(name, urlconf="config.tenant_urls")  # mounted here
                with self.assertRaises(NoReverseMatch):
                    reverse(name, urlconf="config.public_urls")  # but not here
