"""No-DB lock for operator-impersonation audit stamping (Wave C #4 Phase 2).

Phase 1 attributes every request-driven mutation to the acting user (which IS the
operator during impersonation, since request.user is not swapped). Phase 2 adds the
"during impersonation of school X" provenance. These tests pin that stamping without
a DB (AuditLog.objects.create is mocked), so a regression that drops the provenance
fails in CI. The migration apply + DB-backed integration is tracked as ciPending.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.compliance.signals import _impersonation_audit_fields, log_model_save
from apps.observability.logging_context import (
    clear_request_logging_context,
    get_current_during_impersonation,
    get_current_impersonated_school_id,
    set_impersonation_logging_context,
)


class _FakeMeta:
    fields: list = []


class _FakeInstance:
    _meta = _FakeMeta()
    pk = 7

    def __str__(self):
        return "fake-instance"


class _FakeAuditedModel:
    audit_enabled = True


_FakeAuditedModel.__name__ = "FakeAuditedModel"
_FakeAuditedModel.__module__ = "apps.fakeapp.models"


class ImpersonationContextTests(SimpleTestCase):
    def setUp(self):
        clear_request_logging_context()
        self.addCleanup(clear_request_logging_context)

    def test_context_round_trip(self):
        self.assertFalse(get_current_during_impersonation())
        self.assertEqual(get_current_impersonated_school_id(), "")
        set_impersonation_logging_context(True, "school-123")
        self.assertTrue(get_current_during_impersonation())
        self.assertEqual(get_current_impersonated_school_id(), "school-123")

    def test_fields_empty_outside_impersonation(self):
        self.assertEqual(_impersonation_audit_fields(), {})

    def test_fields_populated_during_impersonation(self):
        set_impersonation_logging_context(True, "school-9")
        self.assertEqual(
            _impersonation_audit_fields(),
            {"during_impersonation": True, "impersonated_school_id": "school-9"},
        )

    def test_school_id_truncated_to_64(self):
        set_impersonation_logging_context(True, "x" * 200)
        self.assertEqual(
            len(_impersonation_audit_fields()["impersonated_school_id"]), 64
        )


class AuditSignalImpersonationStampTests(SimpleTestCase):
    def setUp(self):
        clear_request_logging_context()
        self.addCleanup(clear_request_logging_context)

    def test_create_stamps_impersonation(self):
        set_impersonation_logging_context(True, "school-55")
        with mock.patch(
            "apps.compliance.models_audit.AuditLog.objects.create"
        ) as m_create:
            log_model_save(
                sender=_FakeAuditedModel, instance=_FakeInstance(), created=True
            )
        m_create.assert_called_once()
        kwargs = m_create.call_args.kwargs
        self.assertTrue(kwargs.get("during_impersonation"))
        self.assertEqual(kwargs.get("impersonated_school_id"), "school-55")

    def test_create_omits_impersonation_when_normal(self):
        with mock.patch(
            "apps.compliance.models_audit.AuditLog.objects.create"
        ) as m_create:
            log_model_save(
                sender=_FakeAuditedModel, instance=_FakeInstance(), created=True
            )
        m_create.assert_called_once()
        kwargs = m_create.call_args.kwargs
        # Not impersonating -> kwargs omit the provenance so the model default
        # (during_impersonation=False) applies.
        self.assertNotIn("during_impersonation", kwargs)
