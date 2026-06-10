"""Phase 1 tenant boundary core guard — adversarial validation."""

from __future__ import annotations

import uuid

from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings

from apps.tenancy.boundary_core_guard import (
    boundary_bypass,
    make_execute_wrapper,
    pin_tenant_boundary,
    unpin_tenant_boundary,
    verify_orm_filter_kwargs,
    verify_tenant_boundary_scope,
)
from apps.tenancy.exceptions import SecurityIsolationException


class BoundaryGuardUnitTests(SimpleTestCase):
    def test_security_isolation_exception_type(self):
        exc = SecurityIsolationException("denied", detail="test")
        self.assertEqual(exc.code, "tenant_boundary_violation")

    def test_matching_school_id_passes(self):
        sid = str(uuid.uuid4())
        verify_tenant_boundary_scope(
            pinned_school_id=sid,
            orm_kwargs={"school_id": sid},
        )

    def test_foreign_school_id_raises(self):
        pinned = str(uuid.uuid4())
        foreign = str(uuid.uuid4())
        with self.assertRaises(SecurityIsolationException) as ctx:
            verify_tenant_boundary_scope(
                pinned_school_id=pinned,
                orm_kwargs={"school_id": foreign},
            )
        self.assertEqual(ctx.exception.code, "cross_tenant_leak")

    def test_bypass_allows_foreign_during_management(self):
        pinned = str(uuid.uuid4())
        foreign = str(uuid.uuid4())
        with boundary_bypass(reason="test"):
            verify_tenant_boundary_scope(
                pinned_school_id=pinned,
                orm_kwargs={"school_id": foreign},
            )

    def test_sql_literal_mismatch_raises(self):
        pinned = str(uuid.uuid4())
        foreign = str(uuid.uuid4())
        sql = f"SELECT id FROM people_studentprofile WHERE school_id = '{foreign}'"
        with self.assertRaises(SecurityIsolationException):
            verify_tenant_boundary_scope(
                pinned_school_id=pinned,
                sql=sql,
            )

    def test_pin_unpin_lifecycle(self):
        sid = str(uuid.uuid4())
        token = pin_tenant_boundary(school_id=sid, host="demo.runmycampus.com")
        with self.assertRaises(SecurityIsolationException):
            verify_orm_filter_kwargs(
                "people.StudentProfile",
                {"school_id": str(uuid.uuid4())},
            )
        unpin_tenant_boundary(token)


class BoundaryExecuteWrapperTests(TestCase):
    databases = {"default"}

    def test_execute_wrapper_blocks_forged_param(self):
        pinned = str(uuid.uuid4())
        foreign = str(uuid.uuid4())
        token = pin_tenant_boundary(school_id=pinned)
        wrapper = make_execute_wrapper()
        try:
            with connection.execute_wrapper(wrapper):
                with self.assertRaises(SecurityIsolationException):
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f"SELECT 1 WHERE school_id = '{foreign}'"
                        )
        finally:
            unpin_tenant_boundary(token)

    def test_execute_wrapper_allows_matching_param(self):
        pinned = str(uuid.uuid4())
        token = pin_tenant_boundary(school_id=pinned)
        wrapper = make_execute_wrapper()
        try:
            with connection.execute_wrapper(wrapper):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    row = cursor.fetchone()
            self.assertEqual(row[0], 1)
        finally:
            unpin_tenant_boundary(token)


@override_settings(
    MIDDLEWARE=[
        m
        for m in __import__("django.conf", fromlist=["settings"]).settings.MIDDLEWARE
        if "TenantBoundaryCoreGuardMiddleware" in m
    ]
    or [
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "apps.tenancy.middleware.TenantContextMiddleware",
        "apps.tenancy.middleware_boundary_guard.TenantBoundaryCoreGuardMiddleware",
    ]
)
class BoundaryGuardMiddlewareSmokeTests(SimpleTestCase):
    def test_middleware_importable(self):
        from apps.tenancy.middleware_boundary_guard import TenantBoundaryCoreGuardMiddleware

        self.assertTrue(callable(TenantBoundaryCoreGuardMiddleware))
