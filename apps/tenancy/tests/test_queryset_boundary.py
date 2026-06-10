"""Queryset boundary helper tests."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from apps.tenancy.boundary_core_guard import pin_tenant_boundary, unpin_tenant_boundary
from apps.tenancy.exceptions import SecurityIsolationException
from apps.tenancy.queryset_boundary import (
    filter_by_pinned_school,
    scoped_queryset_for_school,
    verify_explicit_school_filter,
)


class QuerysetBoundaryTests(SimpleTestCase):
    def test_scoped_queryset_passes_when_pin_matches(self):
        school = MagicMock()
        school.pk = uuid.uuid4()
        qs = MagicMock()
        qs.model._meta.label = "people.StudentProfile"
        qs.filter.return_value = qs

        token = pin_tenant_boundary(school_id=school.pk)
        try:
            scoped_queryset_for_school(qs, school)
            qs.filter.assert_called_once_with(school=school)
        finally:
            unpin_tenant_boundary(token)

    def test_scoped_queryset_raises_on_pin_mismatch(self):
        school = MagicMock()
        school.pk = uuid.uuid4()
        other = uuid.uuid4()
        qs = MagicMock()
        qs.model._meta.label = "people.StudentProfile"

        token = pin_tenant_boundary(school_id=other)
        try:
            with self.assertRaises(SecurityIsolationException):
                scoped_queryset_for_school(qs, school)
        finally:
            unpin_tenant_boundary(token)

    def test_filter_by_pinned_school_noop_without_pin(self):
        qs = MagicMock()
        qs.model._meta.label = "people.StudentProfile"
        result = filter_by_pinned_school(qs)
        self.assertIs(result, qs)
        qs.filter.assert_not_called()

    def test_verify_explicit_school_filter_accepts_matching_pin(self):
        school_id = uuid.uuid4()
        school = MagicMock()
        school.pk = school_id
        qs = MagicMock()
        qs.model._meta.label = "finance.Invoice"

        token = pin_tenant_boundary(school_id=school_id)
        try:
            verify_explicit_school_filter(qs, school=school)
        finally:
            unpin_tenant_boundary(token)
