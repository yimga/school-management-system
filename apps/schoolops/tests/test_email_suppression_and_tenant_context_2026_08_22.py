"""Two defects on the email path: suppression, and async tenant context.

1. SUPPRESSION WAS FIRST-RECIPIENT-ONLY. ``_send_transactional_sync_core``
   builds ONE message with ``to=to_list``, so every address in the list is
   delivered to. The gate checked ``to_list[0]`` and nothing else, which meant
   anyone who had hard-bounced, complained or unsubscribed kept receiving mail
   for as long as they were not at index 0 -- on the bulk path, where
   multi-recipient is the norm, that is essentially always. Sending to
   known-dead addresses is also what destroys sender reputation, so this is a
   deliverability defect as much as a consent one.

2. THE ASYNC PATHS CARRIED NO TENANT CONTEXT. A daemon thread gets its own DB
   connection, and both the django-tenants schema and the RLS
   ``app.current_school_id`` GUC live on the connection -- so the thread began
   on ``public``. ``EmailDeliveryEvent`` is in apps.schoolops, TENANT_APPS-only,
   so the terminal forensic row went to a schema without that table and
   ``_persist_event``'s ``except Exception`` swallowed it. The in-request
   "queued" marker landed; the row that resolves it never did -- which is the
   exact stuck-send signature the Audit C2 marker was added to expose.

   The Celery alternative was worse: ``worker_kwargs`` carried a School
   INSTANCE, the broker serializer is JSON (CELERY_TASK_SERIALIZER), so
   ``.delay()`` raised EncodeError, the caller logged "falling back to thread"
   and did. The durable path never ran for any send that named a school -- the
   only kind it exists for.
"""

import json
import uuid
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.schoolops import email_delivery
from apps.schoolops.email_delivery import send_transactional, suppress_recipient
from apps.schools.models import School


def _school(tag="mail"):
    slug = f"{tag}-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=f"School {slug}", slug=slug, subdomain=slug, is_active=True
    )


def _ok_core(**kwargs):
    return {
        "ok": True,
        "attempts": 1,
        "delivery_event_id": None,
        "error_kind": "",
        "bounced": False,
        "bounce_kind": "",
    }


class SuppressionAppliesToEveryRecipientTests(TestCase):
    def setUp(self):
        self.good = f"ok-{uuid.uuid4().hex[:8]}@example.com"
        self.dead = f"dead-{uuid.uuid4().hex[:8]}@example.com"
        # "hard_bounce", not "bounce": is_recipient_suppressed only blocks on
        # ("hard_bounce", "complaint", "manual"). Any other reason -- including
        # a marketing unsubscribe -- is deliberately non-blocking for
        # transactional mail, and a typo in the reason silently suppresses
        # nothing at all.
        suppress_recipient(self.dead, reason="hard_bounce")

    def test_a_suppressed_address_after_the_first_is_dropped(self):
        seen = []

        def _spy(**kwargs):
            seen.extend(list(kwargs.get("to") or []))
            return _ok_core()

        with patch.object(
            email_delivery, "_send_transactional_sync_core", side_effect=_spy
        ):
            result = send_transactional(
                subject="Term report", body="hi", to=[self.good, self.dead]
            )

        self.assertTrue(result.get("ok"), result)
        self.assertIn(self.good, seen)
        self.assertNotIn(
            self.dead,
            seen,
            "a suppressed address must never reach the message, whatever its "
            "position in the recipient list",
        )

    def test_all_suppressed_still_short_circuits(self):
        other_dead = f"dead2-{uuid.uuid4().hex[:8]}@example.com"
        suppress_recipient(other_dead, reason="complaint")
        with patch.object(email_delivery, "_send_transactional_sync_core") as core:
            result = send_transactional(
                subject="x", body="y", to=[self.dead, other_dead]
            )
        core.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertTrue(result["suppressed"])
        self.assertEqual(result["error_kind"], "suppressed")

    def test_allow_suppressed_still_bypasses_the_gate(self):
        seen = []

        def _spy(**kwargs):
            seen.extend(list(kwargs.get("to") or []))
            return _ok_core()

        with patch.object(
            email_delivery, "_send_transactional_sync_core", side_effect=_spy
        ):
            send_transactional(
                subject="re-opt-in",
                body="y",
                to=[self.dead],
                allow_suppressed=True,
            )
        self.assertIn(self.dead, seen)


class AsyncSendEntersTenantContextTests(TestCase):
    def setUp(self):
        self.school = _school()

    def test_thread_worker_runs_inside_the_school_tenant_context(self):
        seen = []

        def _record(*, school_id, runnable, **kw):
            seen.append(str(school_id))
            return runnable()

        with patch(
            "apps.schools.celery_tasks._run_with_tenant_context", side_effect=_record
        ), patch.object(email_delivery, "_send_transactional_sync_core") as core:
            email_delivery._async_send_worker(
                subject="s", body="b", to=["a@example.com"], school=self.school
            )

        self.assertEqual(
            seen,
            [str(self.school.pk)],
            "the thread has its own connection, so it must re-enter the "
            "school's tenant context before writing the forensic row",
        )
        core.assert_called_once()

    def test_platform_mail_without_a_school_does_not_try_to_enter_a_tenant(self):
        with patch(
            "apps.schools.celery_tasks._run_with_tenant_context"
        ) as ctx, patch.object(
            email_delivery, "_send_transactional_sync_core"
        ) as core:
            email_delivery._async_send_worker(
                subject="s", body="b", to=["a@example.com"], school=None
            )
        ctx.assert_not_called()
        core.assert_called_once()

    @override_settings(SCHOOLOPS_EMAIL_ASYNC_USE_CELERY=True)
    def test_celery_dispatch_sends_a_school_id_not_a_model_instance(self):
        captured = {}

        def _delay(**kwargs):
            captured.update(kwargs)

        with patch(
            "apps.schoolops.tasks.dispatch_transactional_email.delay",
            side_effect=_delay,
        ):
            result = send_transactional(
                subject="s",
                body="b",
                to=["a@example.com"],
                async_send=True,
                school=self.school,
            )

        self.assertEqual(result.get("transport"), "celery", result)
        self.assertNotIn(
            "school",
            captured,
            "a School instance is not JSON-serializable; sending it made "
            ".delay() raise and silently degraded to the thread",
        )
        self.assertEqual(captured.get("school_id"), str(self.school.pk))
        # Everything the task needs must survive the JSON round-trip.
        json.dumps(captured)

    def test_dispatch_task_reenters_tenant_context_and_resolves_the_school(self):
        from apps.schoolops.tasks import dispatch_transactional_email

        seen = []

        def _record(*, school_id, runnable, **kw):
            seen.append(str(school_id))
            return runnable()

        with patch(
            "apps.schools.celery_tasks._run_with_tenant_context", side_effect=_record
        ), patch(
            "apps.schoolops.email_delivery.send_transactional",
            return_value={"ok": True},
        ) as st:
            out = dispatch_transactional_email(
                subject="s",
                body="b",
                to=["a@example.com"],
                school_id=str(self.school.pk),
            )

        self.assertEqual(out, {"ok": True})
        self.assertEqual(seen, [str(self.school.pk)])
        self.assertEqual(
            st.call_args.kwargs["school"].pk,
            self.school.pk,
            "the task must re-resolve the School so the per-tenant SMTP "
            "override applies, not just the schema",
        )

    def test_dispatch_task_still_accepts_a_legacy_school_kwarg(self):
        from apps.schoolops.tasks import dispatch_transactional_email

        with patch(
            "apps.schoolops.email_delivery.send_transactional",
            return_value={"ok": True},
        ):
            out = dispatch_transactional_email(
                subject="s", body="b", to=["a@example.com"], school=None
            )
        self.assertEqual(out, {"ok": True})

    def test_bulk_dispatch_also_sends_a_school_id(self):
        captured = {}

        with patch(
            "apps.schoolops.tasks.dispatch_bulk_email.delay",
            side_effect=lambda **kw: captured.update(kw),
        ):
            email_delivery.send_bulk(
                subject="s", body="b", to=["a@example.com"], school=self.school
            )

        self.assertEqual(captured.get("school_id"), str(self.school.pk))
        json.dumps(captured)
