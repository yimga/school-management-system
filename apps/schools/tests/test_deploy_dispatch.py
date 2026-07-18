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
from apps.schools.deploy_dispatch import dispatch_setup_email_for_slug
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
