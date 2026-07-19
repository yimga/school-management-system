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


class Migration0078IsInertTests(TestCase):
    """0078 must do NOTHING at migrate time.

    Side-effecting work in a migration (DB writes + SMTP) can poison the outer
    atomic transaction and abort the whole deploy (Render pre-deploy TME seen
    2026-07-19). The owner-setup email now runs OUTSIDE migrate — the management
    command and the tenant-360 operator button — so this node is a guaranteed
    no-op. These tests lock that in so no one reintroduces a migrate-time send.
    """

    def _migration_module(self):
        import importlib

        return importlib.import_module(
            "apps.schools.migrations.0078_dispatch_gilead_tech_setup_email"
        )

    def test_operations_are_a_pure_noop(self):
        from django.db import migrations as dj_migrations

        ops = self._migration_module().Migration.operations
        self.assertEqual(len(ops), 1)
        op = ops[0]
        self.assertIsInstance(op, dj_migrations.RunPython)
        # Both directions are the framework no-op — zero DB side effects.
        self.assertIs(op.code, dj_migrations.RunPython.noop)
        self.assertIs(op.reverse_code, dj_migrations.RunPython.noop)

    def test_no_dispatch_side_effect_remains(self):
        # The old side-effecting _dispatch is gone; nothing runs at migrate time.
        self.assertFalse(hasattr(self._migration_module(), "_dispatch"))
