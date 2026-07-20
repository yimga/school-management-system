"""Deleting a School must work in ``public`` — or say precisely why it cannot.

Two real failures on production-parity Postgres:

1. ``School.objects.filter(...).delete()`` raised
   ``ProgrammingError: relation "portal_portalfeatureitem" does not exist``.
   Django's cascade collector walks EVERY reverse relation; 328 of them are
   tenant tables that do not exist in ``public``. Nothing was deleted, and inside
   an atomic block the error poisoned the transaction.
2. A school that still owns a live tenant schema genuinely CANNOT have its public
   row deleted — 328 cross-schema foreign keys point at it. Failing is correct;
   failing with a mystifying "relation does not exist" is not.

So: skip the tenant relations (their rows go with the schema), and refuse — by
name, with the remedy — when the schema is still there.
"""
from __future__ import annotations

from unittest import mock

from django.test import TestCase

from apps.schools.deletion import (
    PublicSchemaCollector,
    TenantSchemaStillPresent,
    assert_deletable,
    is_tenant_only_model,
    tenant_only_app_labels,
)
from apps.schools.models import School


def _school(slug: str) -> School:
    return School.objects.create(
        name=slug, slug=slug, subdomain=slug, country_code="CM", is_active=True
    )


class TenancySplitTests(TestCase):
    def test_tenant_only_labels_exclude_apps_present_in_public(self):
        labels = tenant_only_app_labels()
        # `schools` is SHARED — it must never be treated as skippable, or
        # deleting a School would stop cascading its own children.
        self.assertNotIn("schools", labels)

    def test_tenant_apps_are_recognised_when_tenancy_is_configured(self):
        with self.settings(
            SHARED_APPS=["apps.schools", "apps.accounts"],
            TENANT_APPS=["apps.portal", "apps.academics"],
        ):
            labels = tenant_only_app_labels()
            self.assertIn("portal", labels)
            self.assertIn("academics", labels)
            self.assertNotIn("schools", labels)

    def test_an_app_listed_on_both_sides_is_not_tenant_only(self):
        """It exists in `public` too, so its rows must still cascade."""
        with self.settings(
            SHARED_APPS=["apps.schools", "apps.portal"],
            TENANT_APPS=["apps.portal", "apps.academics"],
        ):
            labels = tenant_only_app_labels()
            self.assertNotIn("portal", labels)
            self.assertIn("academics", labels)


class PublicSchemaCollectorTests(TestCase):
    def test_collector_skips_tenant_relations_and_still_deletes_the_row(self):
        """The regressed case: the collector used to die walking tenant tables."""
        school = _school("del-skip")
        with self.settings(
            SHARED_APPS=["apps.schools", "apps.accounts", "apps.customers"],
            TENANT_APPS=["apps.portal", "apps.academics", "apps.people"],
        ):
            collector = PublicSchemaCollector(using="default", skip_tenant_relations=True)
            collector.collect([school])
            collector.delete()

        self.assertFalse(School.objects.filter(pk=school.pk).exists())
        self.assertTrue(
            collector.skipped_models,
            "no tenant relation was skipped — the collector would still walk them "
            "into `public`, which is the crash this fix exists to stop",
        )
        self.assertTrue(
            all(lbl.split(".")[0] != "schools" for lbl in collector.skipped_models),
            f"a SHARED relation was skipped: {collector.skipped_models}",
        )

    def test_default_mode_skips_nothing(self):
        """Under RLS (one schema) the stock cascade is correct — change nothing."""
        school = _school("del-noskip")
        collector = PublicSchemaCollector(using="default", skip_tenant_relations=False)
        collector.collect([school])
        collector.delete()
        self.assertEqual(collector.skipped_models, set())


class SchoolDeleteApiTests(TestCase):
    def test_instance_delete_returns_djangos_tuple(self):
        school = _school("del-inst")
        deleted, by_label = school.delete()
        self.assertIsInstance(deleted, int)
        self.assertIsInstance(by_label, dict)
        self.assertFalse(School.objects.filter(slug="del-inst").exists())

    def test_queryset_delete_works(self):
        _school("del-qs-1")
        _school("del-qs-2")
        deleted, _ = School.objects.filter(slug__startswith="del-qs-").delete()
        self.assertGreaterEqual(deleted, 2)
        self.assertFalse(School.objects.filter(slug__startswith="del-qs-").exists())

    def test_live_objects_manager_still_filters_and_deletes(self):
        """`live_objects` gained the queryset — its soft-delete filter must survive."""
        _school("del-live")
        self.assertTrue(School.live_objects.filter(slug="del-live").exists())
        School.live_objects.filter(slug="del-live").delete()
        self.assertFalse(School.objects.filter(slug="del-live").exists())


class TenantSchemaGuardTests(TestCase):
    def test_refuses_and_names_the_schema_when_one_is_still_live(self):
        school = _school("del-guarded")
        with mock.patch(
            "apps.schools.deletion.tenant_schema_for", return_value="s_deadbeef"
        ):
            with self.assertRaises(TenantSchemaStillPresent) as ctx:
                assert_deletable(school)
            message = str(ctx.exception)

        self.assertIn("s_deadbeef", message, "the error must name the schema")
        self.assertIn("drop_schema=True", message, "the error must name the remedy")

    def test_allows_deletion_when_no_schema_exists(self):
        school = _school("del-unguarded")
        assert_deletable(school)  # must not raise
        school.delete()
        self.assertFalse(School.objects.filter(slug="del-unguarded").exists())
