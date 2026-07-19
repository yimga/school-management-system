"""On-deploy setup-email dispatch: targets active owners, fail-soft, test-safe.

The migration 0078 is test-skipped, so it can't cover the logic; this exercises
apps/schools/deploy_dispatch.dispatch_setup_email_for_slug directly (with the mail
send mocked) and confirms the one-time migration function is a no-op under tests.
"""
from __future__ import annotations

import uuid
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.schools.deploy_dispatch import (
    dispatch_setup_email_for_school,
    dispatch_setup_email_for_slug,
)
from apps.schools.models import School, SchoolMembership

_SEND = "apps.schools.welcome_email.send_welcome_email"


def _school(slug, *, active=True):
    return School.objects.create(
        name=f"{slug} School", slug=slug, subdomain=slug, is_active=active
    )


def _owner(school, *, suspended=False):
    user = User.objects.create_user(
        username=f"o-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        password="pass12345678", role=User.Role.ADMIN,
    )
    SchoolMembership.objects.create(
        user=user, school=school, role=User.Role.ADMIN, is_primary=not suspended,
        is_school_owner=True,
        suspended_at=timezone.now() if suspended else None,
    )
    return user


class DispatchSetupEmailTests(TestCase):
    def test_missing_school_is_noop(self):
        with mock.patch(_SEND, return_value=True) as send:
            result = dispatch_setup_email_for_slug("does-not-exist")
        self.assertFalse(result["found"])
        self.assertEqual(result["sent"], 0)
        send.assert_not_called()

    def test_inactive_school_is_noop(self):
        _school("gilead-tech", active=False)
        with mock.patch(_SEND, return_value=True) as send:
            result = dispatch_setup_email_for_slug("gilead-tech")
        self.assertFalse(result["found"])
        send.assert_not_called()

    def test_sends_to_active_owner(self):
        school = _school("gilead-tech")
        owner = _owner(school)
        with mock.patch(_SEND, return_value=True) as send:
            result = dispatch_setup_email_for_slug("gilead-tech")
        self.assertTrue(result["found"])
        self.assertEqual(result["recipients"], 1)
        self.assertEqual(result["sent"], 1)
        send.assert_called_once_with(str(school.pk), owner.email)

    def test_suspended_owner_excluded(self):
        school = _school("gilead-tech")
        active = _owner(school)
        _owner(school, suspended=True)
        with mock.patch(_SEND, return_value=True) as send:
            dispatch_setup_email_for_slug("gilead-tech")
        called = {c.args[1] for c in send.call_args_list}
        self.assertEqual(called, {active.email})

    def test_send_error_is_fail_soft(self):
        school = _school("gilead-tech")
        _owner(school)
        with mock.patch(_SEND, side_effect=RuntimeError("smtp down")):
            result = dispatch_setup_email_for_slug("gilead-tech")  # must not raise
        self.assertEqual(result["sent"], 0)
        self.assertTrue(result["found"])

    def test_reports_configured_true(self):
        school = _school("gilead-tech")
        _owner(school)
        with mock.patch(_SEND, return_value=True), mock.patch(
            "apps.schoolops.email_delivery.transactional_email_configured",
            return_value=True,
        ):
            result = dispatch_setup_email_for_slug("gilead-tech")
        self.assertIs(result["configured"], True)
        self.assertEqual(result["sent"], 1)

    def test_reports_configured_false_and_still_attempts(self):
        # Unconfigured mail must be reported honestly (configured=False) — but the
        # send is still ATTEMPTED (the send layer is authoritative, and a correctly
        # configured deploy must deliver). The loud WARNING log is emitted here too,
        # but the test settings call logging.disable(CRITICAL), so we assert the
        # observable contract (the flag) rather than the swallowed log record.
        school = _school("gilead-tech")
        _owner(school)
        with mock.patch(_SEND, return_value=True) as send, mock.patch(
            "apps.schoolops.email_delivery.transactional_email_configured",
            return_value=False,
        ):
            result = dispatch_setup_email_for_slug("gilead-tech")
        self.assertIs(result["configured"], False)
        send.assert_called_once()

    def test_configured_none_when_preflight_unavailable(self):
        school = _school("gilead-tech")
        _owner(school)
        with mock.patch(_SEND, return_value=True), mock.patch(
            "apps.schoolops.email_delivery.transactional_email_configured",
            side_effect=RuntimeError("import blew up"),
        ):
            result = dispatch_setup_email_for_slug("gilead-tech")
        self.assertIsNone(result["configured"])
        self.assertEqual(result["sent"], 1)


class DispatchForSchoolTests(TestCase):
    """The operator-path sibling: takes a resolved school, no is_active re-filter."""

    def test_none_school_is_noop(self):
        with mock.patch(_SEND, return_value=True) as send:
            result = dispatch_setup_email_for_school(None)
        self.assertFalse(result["found"])
        self.assertEqual(result["sent"], 0)
        send.assert_not_called()

    def test_sends_to_active_owner(self):
        school = _school("gilead-tech")
        owner = _owner(school)
        with mock.patch(_SEND, return_value=True) as send, mock.patch(
            "apps.schoolops.email_delivery.transactional_email_configured",
            return_value=True,
        ):
            result = dispatch_setup_email_for_school(school)
        self.assertTrue(result["found"])
        self.assertEqual(result["recipients"], 1)
        self.assertEqual(result["sent"], 1)
        self.assertIs(result["configured"], True)
        send.assert_called_once_with(str(school.pk), owner.email)

    def test_inactive_school_still_dispatched(self):
        # Unlike the slug path, the operator-chosen school is NOT re-filtered on
        # is_active — the operator is looking right at it and clicked deliberately.
        school = _school("gilead-tech", active=False)
        _owner(school)
        with mock.patch(_SEND, return_value=True) as send:
            result = dispatch_setup_email_for_school(school)
        self.assertTrue(result["found"])
        self.assertEqual(result["recipients"], 1)
        send.assert_called_once()

    def test_suspended_owner_excluded(self):
        school = _school("gilead-tech")
        active = _owner(school)
        _owner(school, suspended=True)
        with mock.patch(_SEND, return_value=True) as send:
            dispatch_setup_email_for_school(school)
        called = {c.args[1] for c in send.call_args_list}
        self.assertEqual(called, {active.email})

    def test_reports_configured_false_and_still_attempts(self):
        school = _school("gilead-tech")
        _owner(school)
        with mock.patch(_SEND, return_value=True) as send, mock.patch(
            "apps.schoolops.email_delivery.transactional_email_configured",
            return_value=False,
        ):
            result = dispatch_setup_email_for_school(school)
        self.assertIs(result["configured"], False)
        send.assert_called_once()

    def test_send_error_is_fail_soft(self):
        school = _school("gilead-tech")
        _owner(school)
        with mock.patch(_SEND, side_effect=RuntimeError("smtp down")):
            result = dispatch_setup_email_for_school(school)  # must not raise
        self.assertEqual(result["sent"], 0)
        self.assertTrue(result["found"])


class MigrationDispatchNoopUnderTestsTests(TestCase):
    def test_migration_function_skips_under_running_tests(self):
        # RUNNING_TESTS is True here, so the migration function must not dispatch,
        # even with a matching active school present.
        import importlib

        school = _school("gilead-tech")
        _owner(school)
        mig = importlib.import_module(
            "apps.schools.migrations.0078_dispatch_gilead_tech_setup_email"
        )
        with mock.patch(
            "apps.schools.deploy_dispatch.dispatch_setup_email_for_slug"
        ) as disp:
            # schema_editor is unused on the RUNNING_TESTS short-circuit path.
            mig._dispatch(apps=None, schema_editor=None)
        disp.assert_not_called()


class MigrationDispatchSavepointIsolationTests(TestCase):
    """0078 must not leave the outer migrate atomic block aborted (Render TME)."""

    def test_savepoint_rollback_when_dispatch_leaves_needs_rollback(self):
        import importlib
        from types import SimpleNamespace

        from django.conf import settings
        from django.test.utils import override_settings

        mig = importlib.import_module(
            "apps.schools.migrations.0078_dispatch_gilead_tech_setup_email"
        )

        class _Conn:
            schema_name = "public"
            needs_rollback = False

            def __init__(self):
                self.rolled_back = []
                self.committed = []

            def savepoint(self):
                return "sid-0078"

            def savepoint_rollback(self, sid):
                self.rolled_back.append(sid)
                self.needs_rollback = False

            def savepoint_commit(self, sid):
                self.committed.append(sid)

        conn = _Conn()

        def _poison_dispatch(_slug):
            # Simulate fail-soft path: DB error was swallowed but Postgres left
            # the connection needing a rollback.
            conn.needs_rollback = True
            return {"found": True, "recipients": 0, "sent": 0, "configured": False}

        schema_editor = SimpleNamespace(connection=conn)
        with override_settings(RUNNING_TESTS=False), mock.patch(
            "apps.schools.deploy_dispatch.dispatch_setup_email_for_slug",
            side_effect=_poison_dispatch,
        ):
            # Ensure the migration sees RUNNING_TESTS=False even if settings_test
            # set it True at import time — override_settings handles that.
            self.assertFalse(settings.RUNNING_TESTS)
            mig._dispatch(apps=None, schema_editor=schema_editor)

        self.assertEqual(conn.rolled_back, ["sid-0078"])
        self.assertEqual(conn.committed, [])
        self.assertFalse(conn.needs_rollback)
