"""
The execute wrapper must see PARAMETERIZED tenant ids, not just inlined literals.

Django emits ``WHERE "t"."school_id" = %s`` with a positional param for every ORM
query and for every well-behaved raw statement, so a guard that only scans the SQL
*text* for an inlined uuid (``_SQL_SCHOOL_LITERAL``) fires exclusively on the one
form the repo's own raw-SQL conventions already forbid. The pre-existing
``test_execute_wrapper_blocks_forged_param`` passes an f-string literal, so it
never exercised the parameterized path at all.
"""

import uuid

from django.db import connection
from django.test import TestCase

from apps.tenancy.boundary_core_guard import (
    make_execute_wrapper,
    pin_tenant_boundary,
    unpin_tenant_boundary,
)
from apps.tenancy.exceptions import SecurityIsolationException


class ParameterizedBoundaryWrapperTests(TestCase):
    databases = {"default"}

    def _wrapped(self, pinned):
        """Pin + install the wrapper; returns a context-manager pair."""
        return pin_tenant_boundary(school_id=pinned), make_execute_wrapper()

    def test_blocks_parameterized_cross_tenant_select(self):
        pinned = str(uuid.uuid4())
        foreign = str(uuid.uuid4())
        token, wrapper = self._wrapped(pinned)
        try:
            with connection.execute_wrapper(wrapper):
                with self.assertRaises(SecurityIsolationException) as ctx:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            'SELECT 1 FROM "schools_schoolmembership" '
                            'WHERE "school_id" = %s',
                            [foreign],
                        )
            # A DatabaseError would NOT satisfy assertRaises above; assert the
            # boundary code as well so a future unrelated raise cannot pass.
            self.assertEqual(ctx.exception.code, "cross_tenant_leak")
        finally:
            unpin_tenant_boundary(token)

    def test_blocks_parameterized_cross_tenant_in_clause(self):
        pinned = str(uuid.uuid4())
        foreign = str(uuid.uuid4())
        token, wrapper = self._wrapped(pinned)
        try:
            with connection.execute_wrapper(wrapper):
                with self.assertRaises(SecurityIsolationException):
                    with connection.cursor() as cursor:
                        cursor.execute(
                            'SELECT 1 FROM "schools_schoolmembership" '
                            'WHERE "school_id" IN (%s, %s)',
                            [pinned, foreign],
                        )
        finally:
            unpin_tenant_boundary(token)

    def test_blocks_cross_tenant_orm_queryset(self):
        """The ORM compiles to placeholders too -- the whole point of the guard."""
        from apps.schools.models import SchoolMembership

        pinned = str(uuid.uuid4())
        foreign = str(uuid.uuid4())
        token, wrapper = self._wrapped(pinned)
        try:
            with connection.execute_wrapper(wrapper):
                with self.assertRaises(SecurityIsolationException):
                    list(SchoolMembership.objects.filter(school_id=foreign))
        finally:
            unpin_tenant_boundary(token)

    def test_allows_matching_parameterized_select(self):
        pinned = str(uuid.uuid4())
        token, wrapper = self._wrapped(pinned)
        try:
            with connection.execute_wrapper(wrapper):
                with connection.cursor() as cursor:
                    cursor.execute(
                        'SELECT 1 FROM "schools_schoolmembership" '
                        'WHERE "school_id" = %s',
                        [pinned],
                    )
                    cursor.fetchall()
        finally:
            unpin_tenant_boundary(token)

    def test_allows_same_uuid_in_undashed_form(self):
        """
        SQLite binds a UUIDField as 32 hex chars with no dashes while the pin is the
        dashed form. Comparing the raw strings would flag every in-tenant query.
        """
        sid = uuid.uuid4()
        token, wrapper = self._wrapped(str(sid))
        try:
            with connection.execute_wrapper(wrapper):
                with connection.cursor() as cursor:
                    cursor.execute(
                        'SELECT 1 FROM "schools_schoolmembership" '
                        'WHERE "school_id" = %s',
                        [sid.hex],
                    )
                    cursor.fetchall()
        finally:
            unpin_tenant_boundary(token)

    def test_non_tenant_placeholders_are_ignored(self):
        """A param that merely happens to be a uuid must not be treated as a tenant id."""
        pinned = str(uuid.uuid4())
        unrelated = str(uuid.uuid4())
        token, wrapper = self._wrapped(pinned)
        try:
            with connection.execute_wrapper(wrapper):
                with connection.cursor() as cursor:
                    cursor.execute(
                        'SELECT 1 FROM "schools_schoolmembership" WHERE "id" = %s',
                        [unrelated],
                    )
                    cursor.fetchall()
        finally:
            unpin_tenant_boundary(token)
