"""Regression seal: AdminInactivityAlert producer.

Bug (2026-06-17 gap analysis): AdminInactivityAlert was read by the operator API but
written nowhere, so the inactivity panel was perpetually empty (same class as the CS
risk-signal producer gap). sync_admin_inactivity_alert now fires the alert when the tenant
has been inactive past the threshold, idempotently (one per window).

Hermetic: patches the model — no DB.
"""
from datetime import timedelta
from unittest import mock

from django.test import SimpleTestCase
from django.utils import timezone

from apps.customersuccess.services import sync_admin_inactivity_alert


def _model(exists):
    m = mock.MagicMock()
    m.objects.filter.return_value.exists.return_value = exists
    return m


class AdminInactivityProducerSealTests(SimpleTestCase):
    def test_inactive_creates_alert(self):
        school = mock.Mock(
            last_activity=timezone.now() - timedelta(days=30),
            created_at=timezone.now() - timedelta(days=60),
        )
        model = _model(exists=False)
        with mock.patch("apps.customersuccess.models.AdminInactivityAlert", model):
            out = sync_admin_inactivity_alert(school)
        self.assertEqual(out, {"created": 1})
        self.assertTrue(model.objects.create.called)

    def test_inactive_but_recent_alert_dedups(self):
        school = mock.Mock(
            last_activity=timezone.now() - timedelta(days=30),
            created_at=timezone.now() - timedelta(days=60),
        )
        model = _model(exists=True)  # an alert already exists in the window
        with mock.patch("apps.customersuccess.models.AdminInactivityAlert", model):
            out = sync_admin_inactivity_alert(school)
        self.assertEqual(out, {"created": 0})
        self.assertFalse(model.objects.create.called)

    def test_active_school_short_circuits(self):
        school = mock.Mock(
            last_activity=timezone.now() - timedelta(days=1),
            created_at=timezone.now() - timedelta(days=60),
        )
        model = _model(exists=False)
        with mock.patch("apps.customersuccess.models.AdminInactivityAlert", model):
            out = sync_admin_inactivity_alert(school)
        self.assertEqual(out, {"created": 0})
        self.assertFalse(model.objects.filter.called, "active tenant must not query")
        self.assertFalse(model.objects.create.called)
