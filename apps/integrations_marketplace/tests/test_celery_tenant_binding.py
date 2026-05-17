"""Tests for v2.89 follow-up: Celery `task_prerun` / `task_postrun` signal
handlers that bind the active tenant for the per-tenant email backend.

DB-free: we stub the resolver path so we don't need a live School row.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.integrations_marketplace import celery_tenant_binding as binding
from apps.integrations_marketplace.email_backend import (
    _active_school,
    clear_tenant_for_email,
)


class _FakeSchool:
    def __init__(self, pk=1):
        self.pk = pk
        # Mimic Django's model _meta sentinel used by the resolver fast-path.
        self._meta = object()


class ResolveSchoolFromKwargsTests(SimpleTestCase):
    def tearDown(self):
        clear_tenant_for_email()

    def test_resolver_prefers_school_instance_in_kwargs(self):
        s = _FakeSchool(pk=42)
        out = binding._resolve_school(
            task_id="t1", sender=None,
            args=(), kwargs={"school": s, "school_id": 999},
        )
        self.assertIs(out, s)

    def test_resolver_hydrates_school_id_when_no_instance(self):
        s = _FakeSchool(pk=7)
        with mock.patch.object(binding, "_hydrate_school", return_value=s) as h:
            out = binding._resolve_school(
                task_id="t2", sender=None,
                args=(), kwargs={"school_id": 7},
            )
        h.assert_called_once_with(7)
        self.assertIs(out, s)

    def test_resolver_falls_through_to_positional_school(self):
        s = _FakeSchool(pk=100)
        out = binding._resolve_school(
            task_id="t3", sender=None,
            args=(s, "extra"), kwargs={},
        )
        self.assertIs(out, s)

    def test_resolver_hydrates_positional_int(self):
        s = _FakeSchool(pk=55)
        with mock.patch.object(binding, "_hydrate_school", return_value=s):
            out = binding._resolve_school(
                task_id="t4", sender=None, args=(55,), kwargs={},
            )
        self.assertIs(out, s)

    def test_resolver_returns_none_when_nothing_matches(self):
        out = binding._resolve_school(
            task_id="t5", sender=None,
            args=(), kwargs={"unrelated": True},
        )
        self.assertIsNone(out)


class HydrateSchoolTests(SimpleTestCase):
    def test_hydrate_school_swallows_db_error(self):
        # Force the .filter() call to raise — must not propagate.
        with mock.patch("apps.schools.models.School.objects.filter",
                        side_effect=RuntimeError("DB down")):
            self.assertIsNone(binding._hydrate_school(1))


class SignalHandlerBindingTests(SimpleTestCase):
    def tearDown(self):
        clear_tenant_for_email()

    def test_prerun_with_school_id_binds_to_thread_local(self):
        s = _FakeSchool(pk=11)
        with mock.patch.object(binding, "_hydrate_school", return_value=s):
            binding._on_task_prerun(
                sender=None, task_id="abc", task=None,
                args=(), kwargs={"school_id": 11},
            )
        self.assertIs(_active_school({}), s)

    def test_prerun_with_no_school_does_not_bind(self):
        binding._on_task_prerun(
            sender=None, task_id="abc", task=None,
            args=(), kwargs={"unrelated": "x"},
        )
        self.assertIsNone(_active_school({}))

    def test_postrun_clears_thread_local(self):
        s = _FakeSchool(pk=22)
        with mock.patch.object(binding, "_hydrate_school", return_value=s):
            binding._on_task_prerun(
                sender=None, task_id="abc", task=None,
                args=(), kwargs={"school_id": 22},
            )
        self.assertIsNotNone(_active_school({}))
        binding._on_task_postrun(
            sender=None, task_id="abc", task=None,
            args=(), kwargs={}, retval=None, state="SUCCESS",
        )
        self.assertIsNone(_active_school({}))

    def test_prerun_swallows_resolver_exception(self):
        # If the resolver explodes for any reason, the task must still run.
        with mock.patch.object(
            binding, "_resolve_school", side_effect=RuntimeError("boom")
        ):
            # Must NOT raise.
            binding._on_task_prerun(
                sender=None, task_id="abc", task=None,
                args=(), kwargs={"school_id": 1},
            )
        self.assertIsNone(_active_school({}))


class MiddlewareWiredIntoSettingsTests(SimpleTestCase):
    """Catch accidental removal of TenantEmailBindingMiddleware from MIDDLEWARE.

    Without it, every email sent inside a request falls back to global ANYMAIL
    settings — the v2.79 per-tenant isolation silently breaks. This test is
    the cheapest backstop against that regression.
    """

    def test_tenant_email_binding_middleware_is_in_middleware(self):
        from django.conf import settings
        target = (
            "apps.integrations_marketplace.middleware.TenantEmailBindingMiddleware"
        )
        self.assertIn(target, settings.MIDDLEWARE)

    def test_tenant_email_binding_middleware_runs_after_tenant_middleware(self):
        # Ordering matters: TenantMiddleware sets request.school; our middleware
        # consumes it. If someone reorders us above TenantMiddleware, the
        # binding silently becomes a no-op.
        from django.conf import settings
        mw = list(settings.MIDDLEWARE)
        tenant_idx = mw.index("apps.schools.middleware.TenantMiddleware")
        binding_idx = mw.index(
            "apps.integrations_marketplace.middleware.TenantEmailBindingMiddleware"
        )
        self.assertGreater(binding_idx, tenant_idx)
