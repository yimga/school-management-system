from __future__ import annotations

from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase
from django.utils.translation import activate

from apps.siteconfig.admin_page_aware_rail import (
    build_app_index_rail,
    build_change_form_rail,
    build_changelist_rail,
    build_guided_surface_rail,
    build_index_rail,
)


class _UserStub:
    pk = 7

    def __str__(self) -> str:
        return "admin"


class AdminPageAwareRailTests(SimpleTestCase):
    def setUp(self):
        activate("en")
        self.request = RequestFactory().get("/admin/accounts/user/1/change/")

    def test_change_form_rail_is_model_aware(self):
        opts = SimpleNamespace(
            app_label="accounts",
            model_name="user",
            verbose_name="user",
            verbose_name_plural="users",
        )
        rail = build_change_form_rail(
            request=self.request,
            opts=opts,
            original=_UserStub(),
            add=False,
            change=True,
            is_manager_host=True,
            admin_outcome_deck={
                "admin_deck_links": [
                    {"label": "Access center", "url": "/super/access/"},
                ]
            },
        )
        self.assertEqual(rail["surface"], "change-form")
        self.assertIn("accounts", rail["boundary_strong"])
        self.assertTrue(rail["pulse_enabled"])
        labels = {f["label"] for f in rail["facts"]}
        self.assertIn("App", labels)
        self.assertIn("Primary key", labels)
        self.assertTrue(any(l["label"] == "Access center" for l in rail["guided"]))

    def test_changelist_rail_counts(self):
        opts = SimpleNamespace(
            app_label="accounts",
            model_name="user",
            verbose_name="user",
            verbose_name_plural="users",
        )
        cl = SimpleNamespace(
            result_count=12,
            full_result_count=40,
            has_filters=True,
            has_active_filters=True,
            page_num=2,
            opts=opts,
        )
        rail = build_changelist_rail(
            request=self.request,
            opts=opts,
            cl=cl,
            is_manager_host=True,
        )
        self.assertEqual(rail["surface"], "change-list")
        self.assertFalse(rail["pulse_enabled"])
        values = " ".join(f["value"] for f in rail["facts"])
        self.assertIn("12", values)
        self.assertIn("40", values)

    def test_index_rail_catalog_density(self):
        catalog = [
            SimpleNamespace(models=[1, 2, 3]),
            {"models": [1, 2]},
        ]
        rail = build_index_rail(
            request=self.request,
            is_manager_host=True,
            admin_catalog=catalog,
        )
        self.assertEqual(rail["surface"], "index")
        values = {f["label"]: f["value"] for f in rail["facts"]}
        self.assertEqual(values["Catalog sections"], "2")
        self.assertEqual(values["Models listed"], "5")

    def test_app_index_rail_model_density(self):
        models = [
            {"name": "User", "add_url": "/admin/accounts/user/add/"},
            SimpleNamespace(name="Group", add_url=""),
        ]
        rail = build_app_index_rail(
            request=self.request,
            is_manager_host=True,
            app_label="accounts",
            title="Accounts",
            models=models,
        )
        self.assertEqual(rail["surface"], "app-index")
        values = {f["label"]: f["value"] for f in rail["facts"]}
        self.assertEqual(values["Models"], "2")
        self.assertEqual(values["Addable"], "1")

    def test_guided_surface_rail_defaults(self):
        rail = build_guided_surface_rail(
            request=self.request,
            is_manager_host=True,
            page_title="Waive subscription",
            page_lede="Note required",
        )
        self.assertEqual(rail["surface"], "guided")
        self.assertTrue(rail["facts"])
        self.assertIn("Waive", rail["page_title"])

    def test_change_form_rail_omits_history_link(self):
        opts = SimpleNamespace(
            app_label="accounts",
            model_name="user",
            verbose_name="user",
            verbose_name_plural="users",
        )
        rail = build_change_form_rail(
            request=self.request,
            opts=opts,
            original=_UserStub(),
            add=False,
            change=True,
            has_absolute_url=True,
            absolute_url="/u/1/",
            is_manager_host=True,
        )
        labels = {l["label"] for l in rail["links"]}
        self.assertNotIn("History", labels)
        self.assertNotIn("View on site", labels)
