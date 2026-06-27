"""No-DB lock for audit actor attribution (Wave C #4, Phase 1).

The auto CREATE/UPDATE/DELETE audit signals run at the ORM layer and historically
wrote every model-mutation AuditLog row with ``user=None`` (WHAT but not WHO).
Phase 1 attributes request-driven mutations to the acting user by reading the
observability request contextvar. These tests pin that behavior without a DB
(AuditLog.objects.create is mocked), so a regression that drops attribution
fails in CI.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.compliance.signals import (
    _current_actor_id,
    log_model_delete,
    log_model_save,
)
from apps.observability.logging_context import (
    clear_request_logging_context,
    get_current_school_id,
    get_current_user_id,
    set_request_logging_context,
)


class _FakeMeta:
    fields: list = []


class _FakeInstance:
    _meta = _FakeMeta()
    pk = 7

    def __str__(self):
        return "fake-instance"


class _FakeAuditedModel:
    """Stand-in sender: opted into audit, not a skipped/Django model."""

    audit_enabled = True


# Give the fake sender a name + module the signal's guards accept.
_FakeAuditedModel.__name__ = "FakeAuditedModel"
_FakeAuditedModel.__module__ = "apps.fakeapp.models"


class CurrentActorIdTests(SimpleTestCase):
    def setUp(self):
        clear_request_logging_context()
        self.addCleanup(clear_request_logging_context)

    def test_returns_int_for_authenticated_context(self):
        set_request_logging_context(user_id="42")
        self.assertEqual(_current_actor_id(), 42)
        self.assertEqual(get_current_user_id(), "42")

    def test_returns_none_outside_request(self):
        self.assertIsNone(_current_actor_id())

    def test_returns_none_for_non_numeric_user_id(self):
        set_request_logging_context(user_id="anonymous")
        self.assertIsNone(_current_actor_id())

    def test_school_accessor_reads_context(self):
        set_request_logging_context(user_id="1", school_id="9")
        self.assertEqual(get_current_school_id(), "9")


class AuditSignalAttributionTests(SimpleTestCase):
    def setUp(self):
        clear_request_logging_context()
        self.addCleanup(clear_request_logging_context)

    def test_create_attributes_acting_user(self):
        set_request_logging_context(user_id="55")
        with mock.patch(
            "apps.compliance.models_audit.AuditLog.objects.create"
        ) as m_create:
            log_model_save(
                sender=_FakeAuditedModel, instance=_FakeInstance(), created=True
            )
        m_create.assert_called_once()
        self.assertEqual(m_create.call_args.kwargs.get("user_id"), 55)

    def test_delete_attributes_acting_user(self):
        set_request_logging_context(user_id="55")
        with mock.patch(
            "apps.compliance.models_audit.AuditLog.objects.create"
        ) as m_create:
            log_model_delete(sender=_FakeAuditedModel, instance=_FakeInstance())
        m_create.assert_called_once()
        self.assertEqual(m_create.call_args.kwargs.get("user_id"), 55)

    def test_system_write_stays_unattributed(self):
        # No request context -> user_id None (unchanged legacy behavior).
        with mock.patch(
            "apps.compliance.models_audit.AuditLog.objects.create"
        ) as m_create:
            log_model_save(
                sender=_FakeAuditedModel, instance=_FakeInstance(), created=True
            )
        m_create.assert_called_once()
        self.assertIsNone(m_create.call_args.kwargs.get("user_id"))

    def test_non_audited_model_is_skipped(self):
        class _Unaudited:
            audit_enabled = False

        _Unaudited.__name__ = "Unaudited"
        _Unaudited.__module__ = "apps.fakeapp.models"

        with mock.patch(
            "apps.compliance.models_audit.AuditLog.objects.create"
        ) as m_create:
            log_model_save(sender=_Unaudited, instance=_FakeInstance(), created=True)
        m_create.assert_not_called()
