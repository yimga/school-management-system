"""The ownership audit must inspect the SCHOOL's schema, not whichever one it lands on.

Run live against gilead-tech on 2026-08-20, ``repair_sync_ownership --school
gilead-tech`` reported **572 unowned rows**. The tenant's actual schema held 420
correctly-owned students, 114 subjects, 14 classrooms — and exactly ONE unowned row.
The audit had been reading ``public``, because nothing in ``ownership_repair`` ever
entered tenant context.

The consequence is not a cosmetic miscount. ``--apply`` writes ``school_id`` onto rows
the audit selected, so an operator acting on that report would have stamped a school's
ownership onto public-schema rows on the strength of an audit that never looked at the
school.

Why it survived review: a sovereign box runs ``USE_DJANGO_TENANTS=0`` (shared DB +
RLS, one schema), where the missing switch is a genuine no-op. The code was written
and exercised in the one configuration that cannot exhibit the bug.

These tests assert the SWITCH, not the counts — the query itself was never in doubt.
"""
from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase, override_settings


class FakeSchool:
    def __init__(self, schema_name="s_deadbeef", pk="school-1"):
        self.schema_name = schema_name
        self.pk = pk


class SchoolSchemaSwitchTests(SimpleTestCase):
    """``_school_schema`` is the whole fix; pin exactly when it engages."""

    @override_settings(USE_DJANGO_TENANTS=True)
    def test_enters_the_schools_schema_when_tenancy_is_on(self):
        from apps.sync_engine.ownership_repair import _school_schema

        with mock.patch("django_tenants.utils.schema_context") as ctx:
            with _school_schema(FakeSchool("s_f984ea95")):
                pass
        ctx.assert_called_once_with("s_f984ea95")

    @override_settings(USE_DJANGO_TENANTS=False)
    def test_is_a_no_op_on_a_box_which_has_only_one_schema(self):
        from apps.sync_engine.ownership_repair import _school_schema

        with mock.patch("django_tenants.utils.schema_context") as ctx:
            with _school_schema(FakeSchool("s_f984ea95")):
                pass
        ctx.assert_not_called()

    @override_settings(USE_DJANGO_TENANTS=True)
    def test_a_school_without_a_schema_name_does_not_switch(self):
        from apps.sync_engine.ownership_repair import _school_schema

        with mock.patch("django_tenants.utils.schema_context") as ctx:
            with _school_schema(FakeSchool("")):
                pass
        ctx.assert_not_called()

    @override_settings(USE_DJANGO_TENANTS=True)
    def test_the_body_still_runs_when_django_tenants_is_absent(self):
        """A box image without django_tenants must not crash the audit."""
        import builtins

        from apps.sync_engine.ownership_repair import _school_schema

        real_import = builtins.__import__

        def no_django_tenants(name, *args, **kwargs):
            if name == "django_tenants.utils":
                raise ImportError("not installed")
            return real_import(name, *args, **kwargs)

        ran = []
        with mock.patch.object(builtins, "__import__", side_effect=no_django_tenants):
            with _school_schema(FakeSchool("s_x")):
                ran.append(True)
        self.assertEqual(ran, [True])


class AuditUsesTheSwitchTests(SimpleTestCase):
    """Both entry points must be inside the context manager, not merely near it."""

    def test_plan_and_apply_both_wrap_their_queries(self):
        import inspect

        from apps.sync_engine import ownership_repair

        source = inspect.getsource(ownership_repair)
        plan_src = source.split("def plan_ownership_repair", 1)[1].split("\ndef ", 1)[0]
        apply_src = source.split("def apply_ownership_repair", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("_school_schema(school)", plan_src)
        self.assertIn("_school_schema(school)", apply_src)
