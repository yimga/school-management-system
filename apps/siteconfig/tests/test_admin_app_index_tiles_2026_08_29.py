"""The admin app-index must render a NAMED, REACHABLE tile per model.

Reported 2026-08-28 against the tenant admin (People Management): every tile on
the app-index rendered as an empty card carrying only "+ Add" -- no model name,
no changelist link. The count was right (17 cards, 16 addable), so the rows were
reaching the page; only the label and the link were missing.

Both admin sites are covered, each under ITS OWN urlconf. The admin namespace
lives in ``config.tenant_urls`` and ``config.manager_urls``, not in
``config.urls`` -- reverse under the wrong one raises "'admin' is not a
registered namespace", which is a broken probe rather than a product defect. The
app label is also resolved per site instead of assumed: the two sites register
different apps, and hardcoding one yields a 404 that looks like a finding.
"""

from __future__ import annotations

import pathlib
import re
import unittest
import uuid

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import get_urlconf, set_urlconf

from apps.siteconfig.tests.test_admin import (
    _admin_request_with_session_and_messages,
)
from config.admin import platform_admin_site, tenant_admin_site

User = get_user_model()

_MANAGER_URLCONF = "config.manager_urls"
_TENANT_URLCONF = "config.tenant_urls"
_MANAGER_HOST = "manager.runmycampus.com"
_TENANT_BASE_DOMAIN = "runmycampus.com"


@override_settings(
    ROOT_URLCONF=_TENANT_URLCONF,
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _MANAGER_HOST],
    MULTI_TENANT_BASE_DOMAIN=_TENANT_BASE_DOMAIN,
)
class AdminAppIndexTileContractTests(TestCase):
    """A tile the user cannot read or click is not a rendered tile."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = User.objects.create_superuser(
            username=f"appindex-tile-{uuid.uuid4().hex[:8]}",
            email=f"appindex-tile-{uuid.uuid4().hex[:8]}@example.com",
            password="probe-password",
        )

    def setUp(self) -> None:
        super().setUp()
        self._prev_urlconf = get_urlconf()

    def tearDown(self) -> None:
        set_urlconf(self._prev_urlconf)
        super().tearDown()

    # -- harness ---------------------------------------------------------------

    def _request(self, urlconf: str, path: str):
        set_urlconf(urlconf)
        request = _admin_request_with_session_and_messages(
            RequestFactory(), self.user, path
        )
        request.urlconf = urlconf
        return request

    def _widest_app_label(self, site, urlconf: str) -> str:
        """The app on THIS site with the most models.

        The two sites register different apps, so the widest app-index surface
        is site-specific. Picking it dynamically also means this test keeps
        pointing at the biggest grid as registration changes.
        """
        request = self._request(urlconf, "/admin/")
        app_list = site.get_app_list(request)
        best, best_n = "", -1
        for app in app_list:
            models = app.get("models") if isinstance(app, dict) else None
            n = len(models or [])
            if n > best_n:
                best, best_n = app.get("app_label") or "", n
        return best

    def _app_index_rows(self, site, urlconf: str) -> tuple[list[dict], object]:
        app_label = self._widest_app_label(site, urlconf)
        self.assertTrue(app_label, "no app registered on this admin site")
        request = self._request(urlconf, f"/admin/{app_label}/")
        response = site.app_index(request, app_label)
        context = response.context_data

        # The template prefers admin_app_index_models and falls back to
        # app_list. Read whichever will actually paint.
        enriched = context.get("admin_app_index_models") or []
        if enriched:
            return list(enriched), response
        rows: list[dict] = []
        for app in context.get("app_list") or []:
            models = app.get("models") if isinstance(app, dict) else None
            rows.extend(list(models or []))
        return rows, response

    # -- contract --------------------------------------------------------------

    def test_tenant_app_index_rows_are_named(self) -> None:
        rows, _ = self._app_index_rows(tenant_admin_site, _TENANT_URLCONF)
        self.assertTrue(rows, "tenant app-index produced no model rows at all")
        unnamed = [r for r in rows if not str(r.get("name") or "").strip()]
        self.assertEqual(
            unnamed,
            [],
            f"{len(unnamed)}/{len(rows)} tenant tiles would render with no label",
        )

    def test_tenant_app_index_rows_are_reachable(self) -> None:
        rows, _ = self._app_index_rows(tenant_admin_site, _TENANT_URLCONF)
        self.assertTrue(rows, "tenant app-index produced no model rows at all")
        unreachable = [
            str(r.get("object_name") or r.get("name") or "?")
            for r in rows
            if not str(r.get("admin_url") or "").strip()
        ]
        self.assertEqual(
            unreachable,
            [],
            f"{len(unreachable)}/{len(rows)} tenant tiles have no changelist link",
        )

    def test_tenant_app_index_paints_the_names_into_the_html(self) -> None:
        # Rows can be correct while the page still renders blank, so assert on
        # the response BODY as well as the context.
        rows, response = self._app_index_rows(tenant_admin_site, _TENANT_URLCONF)
        self.assertTrue(rows, "tenant app-index produced no model rows at all")
        html = response.render().content.decode("utf-8", errors="ignore")
        missing = [
            name
            for name in (str(r.get("name") or "").strip() for r in rows)
            if name and name not in html
        ]
        self.assertEqual(
            missing, [], f"names absent from the rendered page: {missing[:5]}"
        )

    def test_operator_app_index_rows_are_named(self) -> None:
        rows, _ = self._app_index_rows(platform_admin_site, _MANAGER_URLCONF)
        self.assertTrue(rows, "operator app-index produced no model rows at all")
        unnamed = [r for r in rows if not str(r.get("name") or "").strip()]
        self.assertEqual(
            unnamed,
            [],
            f"{len(unnamed)}/{len(rows)} operator tiles would render with no label",
        )

    def test_operator_app_index_rows_are_reachable(self) -> None:
        rows, _ = self._app_index_rows(platform_admin_site, _MANAGER_URLCONF)
        self.assertTrue(rows, "operator app-index produced no model rows at all")
        unreachable = [
            str(r.get("object_name") or r.get("name") or "?")
            for r in rows
            if not str(r.get("admin_url") or "").strip()
        ]
        self.assertEqual(
            unreachable,
            [],
            f"{len(unreachable)}/{len(rows)} operator tiles have no changelist link",
        )


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CONTRAST_CSS = REPO_ROOT / "static" / "css" / "theme-platform-contrast.css"


def _specificity(selector: str) -> tuple[int, int, int]:
    """(ids, classes, elements) for one selector.

    ``:not(x)`` contributes the specificity of x, which is the whole point
    here: the accent rule earns three extra class-points from its :not()
    chain, and a naive counter that ignores them concludes the override wins
    when it does not.
    """
    sel = selector.strip()
    inner = " ".join(re.findall(r":not\(([^)]*)\)", sel))
    bare = re.sub(r":not\([^)]*\)", " ", sel)
    both = bare + ' ' + inner
    ids = len(re.findall(r"#[\w-]+", both))
    classes = len(re.findall(r"\.[\w-]+", both))
    classes += len(re.findall(r"\[[^\]]+\]", both))
    elements = len(re.findall(r"(?:^|[\s>+~])([a-zA-Z][\w-]*)", both))
    return (ids, classes, elements)


class AppIndexTileTitleColourTests(unittest.TestCase):
    """The tile TITLE must take title colour, not the school brand accent.

    theme-platform-contrast.css paints every <a> in the main region with
    ``--school-accent``. That is correct for a content hyperlink and wrong for
    the app-index tile title, which is a card heading that happens to be a
    link. Measured 2026-08-29 in Chromium over the real rendered page: the
    accent gave contrast 2.54 against the light card (WCAG AA needs 4.5), and
    a school whose accent sits near the card background loses the title
    outright. It also rendered the SAME title in two different colours
    depending on view permission, because the template emits a <span> rather
    than an <a> in that case and the accent rule does not match spans.
    """

    def setUp(self) -> None:
        self.css = CONTRAST_CSS.read_text(encoding="utf-8", errors="ignore")

    def test_a_tile_title_rule_exists(self) -> None:
        self.assertIn(
            "admin-app-index__card-link",
            self.css,
            "no tile-title colour rule: the accent rule wins by default",
        )

    def test_tile_title_outranks_the_accent_rule(self) -> None:
        accent = [
            s
            for s in re.findall(r"^#cp-main-content a:not[^,{]*", self.css, re.M)
        ]
        self.assertTrue(accent, "accent rule not found -- selector renamed?")
        title = [
            s
            for s in re.findall(
                r"^#cp-main-content a\.admin-app-index__card-link[^,{]*",
                self.css,
                re.M,
            )
        ]
        self.assertTrue(
            title, "no #cp-main-content tile-title selector to beat the accent"
        )
        self.assertGreater(
            _specificity(title[0]),
            _specificity(accent[0]),
            f"tile title {_specificity(title[0])} does not outrank accent "
            f"{_specificity(accent[0])}; the title would still be painted "
            "with the school brand colour",
        )

    def test_the_specificity_helper_actually_discriminates(self) -> None:
        # The assertion above passes by comparing two numbers, so it is only
        # worth as much as this helper. Pin the :not() handling that the whole
        # comparison turns on.
        accent = "#cp-main-content a:not(.btn):not(.nav-link):not(.cp-btn)"
        title = (
            "#cp-main-content a.admin-app-index__card-link"
            ":not(.btn):not(.nav-link):not(.cp-btn)"
        )
        self.assertEqual(_specificity(accent), (1, 3, 1))
        self.assertEqual(_specificity(title), (1, 4, 1))
        self.assertGreater(_specificity(title), _specificity(accent))
        # and a selector that merely looks longer must NOT win
        weak = "#cp-main-content .admin-app-index__card-link"
        self.assertLess(_specificity(weak), _specificity(accent))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
