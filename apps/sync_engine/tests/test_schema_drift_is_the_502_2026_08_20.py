"""Schema drift on ONE tenant looks exactly like "the cloud is down". It is not.

OBSERVED IN PRODUCTION, 2026-08-20. The gilead-tech cloud logged:

    gap-fill provisioning failed for bundle 84:
    column academics_academicyear.is_soft_closed does not exist

``academics.AcademicYear`` is a SYNCED entity and ``apps.academics`` is a TENANT
app, so ``is_soft_closed`` (migration ``academics.0083``) arrives per schema via
``migrate_schemas --tenant`` — which applies schema by schema and can therefore
land for some tenants and not others. Building a sync bundle selects every
concrete field, so one absent column raises ``ProgrammingError`` on EVERY bundle
build for that tenant. Django turns that into a 500 and the platform's proxy
serves it to the box as a **502**.

That is why the box reported "cloud gateway error" and why the operator was sent
to check ``RMC_EDGE_OPERATOR_BASE`` — a setting with nothing to do with it. From
the box, a tenant whose schema is one column behind is indistinguishable from a
cloud that is down.

These tests pin the detector, and the sharpest one is the NEGATIVE: a fully
migrated schema must report nothing, because a verifier that cries wolf on a
healthy deployment is one nobody runs on an unhealthy one.
"""
from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase


def _command():
    from apps.sync_engine.management.commands.check_edge_sync_deploy_readiness import (
        Command,
    )

    cmd = Command()
    # The command writes progress through self.stdout; a bare instance has none.
    cmd.stdout = mock.MagicMock()
    cmd.style = mock.MagicMock()
    return cmd


def _academic_year_table():
    from apps.academics.models import AcademicYear

    return AcademicYear._meta.db_table


def _all_columns_of(model):
    return [f.column for f in model._meta.concrete_fields if getattr(f, "column", None)]


class ModelColumnDriftTests(SimpleTestCase):
    def test_a_fully_migrated_schema_reports_nothing(self):
        """The negative that keeps the detector trustworthy."""
        from apps.api.sync_services import _get_entity_config

        entities = _get_entity_config(include_derived=True)

        def every_column(table, schema=""):
            for config in entities.values():
                model = config[0] if isinstance(config, (tuple, list)) else config
                if model._meta.db_table == table:
                    return _all_columns_of(model)
            return []

        cmd = _command()
        with mock.patch.object(cmd, "_columns", side_effect=every_column):
            self.assertEqual(cmd._model_column_drift("s_test", "s_test"), [])

    def test_the_exact_production_failure_is_caught(self):
        """Drop is_soft_closed from academics_academicyear — the real 2026-08-20 state."""
        from apps.api.sync_services import _get_entity_config

        entities = _get_entity_config(include_derived=True)
        year_table = _academic_year_table()

        def columns_missing_soft_closed(table, schema=""):
            for config in entities.values():
                model = config[0] if isinstance(config, (tuple, list)) else config
                if model._meta.db_table == table:
                    cols = _all_columns_of(model)
                    if table == year_table:
                        cols = [c for c in cols if c != "is_soft_closed"]
                    return cols
            return []

        cmd = _command()
        with mock.patch.object(cmd, "_columns", side_effect=columns_missing_soft_closed):
            found = cmd._model_column_drift("s_gilead", "s_gilead")

        self.assertEqual(len(found), 1, found)
        message = found[0]
        self.assertIn(year_table, message)
        self.assertIn("is_soft_closed", message)
        self.assertIn("s_gilead", message)
        # The operator must be told what to RUN, not merely what is wrong.
        self.assertIn("migrate_schemas --tenant", message)
        # ...and why it presents as a 502, because that is the wrong trail they are on.
        self.assertIn("502", message)

    def test_an_absent_table_is_left_to_the_anchor_check(self):
        """Reported once, by the check that already speaks to it — not twice."""
        cmd = _command()
        with mock.patch.object(cmd, "_columns", return_value=[]):
            self.assertEqual(cmd._model_column_drift("s_test", "s_test"), [])

    def test_a_broken_registry_never_takes_the_verifier_down(self):
        cmd = _command()
        with mock.patch(
            "apps.api.sync_services._get_entity_config",
            side_effect=RuntimeError("boom"),
        ):
            self.assertEqual(cmd._model_column_drift("s_test", "s_test"), [])

    def test_academic_year_really_is_on_the_sync_rail(self):
        """If this ever stops being true the production story above changes."""
        from apps.api.sync_services import _get_entity_config

        self.assertIn("academic_year", _get_entity_config(include_derived=True))

    def test_is_soft_closed_really_is_a_concrete_column(self):
        """Guards against the test passing because the field was renamed away."""
        from apps.academics.models import AcademicYear

        self.assertIn("is_soft_closed", _all_columns_of(AcademicYear))
