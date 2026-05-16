"""Tests for the env-configurable control-plane operator-role cascade.

Closes the v2.65.0 follow-up — `CONTROL_PLANE_OPERATOR_ROLES` env var now
drives the operator allowlist used by `user_has_control_plane_access`. The
default behaviour (only SUPERADMIN + is_superuser pass) is unchanged; an
env override extends the allowlist without code changes.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.schools.control_plane import (
    _operator_roles,
    user_has_control_plane_access,
)


def _user(**kw) -> SimpleNamespace:
    return SimpleNamespace(
        **{"is_authenticated": True, "is_superuser": False, "role": "", **kw}
    )


class OperatorRolesEnvCascadeTests(SimpleTestCase):
    def test_default_allowlist_is_superadmin_only(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CONTROL_PLANE_OPERATOR_ROLES", None)
            self.assertEqual(_operator_roles(), frozenset({"SUPERADMIN"}))

    def test_env_override_extends_allowlist(self):
        with mock.patch.dict(
            os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN,ADMIN,IT_ADMIN"}
        ):
            self.assertEqual(
                _operator_roles(),
                frozenset({"SUPERADMIN", "ADMIN", "IT_ADMIN"}),
            )

    def test_env_override_is_case_insensitive_and_strips_whitespace(self):
        with mock.patch.dict(
            os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": " superadmin , admin "}
        ):
            self.assertEqual(_operator_roles(), frozenset({"SUPERADMIN", "ADMIN"}))

    def test_empty_env_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": ""}):
            self.assertEqual(_operator_roles(), frozenset({"SUPERADMIN"}))


class UserHasControlPlaneAccessTests(SimpleTestCase):
    def test_anonymous_blocked(self):
        self.assertFalse(
            user_has_control_plane_access(SimpleNamespace(is_authenticated=False))
        )

    def test_django_superuser_always_passes(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CONTROL_PLANE_OPERATOR_ROLES", None)
            self.assertTrue(user_has_control_plane_access(_user(is_superuser=True)))

    def test_superadmin_role_passes_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CONTROL_PLANE_OPERATOR_ROLES", None)
            self.assertTrue(user_has_control_plane_access(_user(role="SUPERADMIN")))

    def test_admin_role_blocked_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CONTROL_PLANE_OPERATOR_ROLES", None)
            self.assertFalse(user_has_control_plane_access(_user(role="ADMIN")))

    def test_admin_role_allowed_when_env_extends_allowlist(self):
        with mock.patch.dict(
            os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN,ADMIN"}
        ):
            self.assertTrue(user_has_control_plane_access(_user(role="ADMIN")))

    def test_role_check_is_case_insensitive(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CONTROL_PLANE_OPERATOR_ROLES", None)
            self.assertTrue(user_has_control_plane_access(_user(role="superadmin")))

    def test_unrelated_role_still_blocked_after_env_override(self):
        with mock.patch.dict(
            os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN,ADMIN"}
        ):
            self.assertFalse(user_has_control_plane_access(_user(role="TEACHER")))

    def test_blank_role_blocked(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CONTROL_PLANE_OPERATOR_ROLES", None)
            self.assertFalse(user_has_control_plane_access(_user(role="")))
