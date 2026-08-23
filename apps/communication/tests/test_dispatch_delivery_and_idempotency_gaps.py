"""Regression tests for four dead/incorrect communication paths.

1. ``dispatch.get_preference`` returned ``None`` for every user on the platform
   (nothing ever writes a ``communication.NotificationPreference`` row), so the
   mute / channel-override / quiet-hours layer was inert and a parent who
   unticked SMS still got the SMS.
2. ``_sms_idempotency_reserve`` treated a previously FAILED ledger row as a
   duplicate, so a retried SMS was reported "sent" without the provider ever
   being called.
3. ``group_detail`` wrote the @mention rows AFTER ``ThreadMessage.objects.create``,
   and with no ``ATOMIC_REQUESTS`` the ``on_commit`` notification hook had
   already run — so the mute-piercing mention notification never fired.
4. ``AnnouncementViewSet.create`` published without fanning out, and the periodic
   sweep skipped it forever because ``scheduled_at`` was NULL.
"""

import uuid
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import User
from apps.communication import views_groups
from apps.communication.dispatch import dispatch_event, get_preference
from apps.communication.models import (
    Announcement,
    MessageThread,
    SmsSendLog,
    ThreadMute,
)
from apps.communication.notification_service import (
    _sms_idempotency_reserve,
    send_sms,
)
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models_tooling import UserPreference


def _mk_school(tag):
    return School.objects.create(
        name=f"{tag} School",
        slug=f"{tag}-{uuid.uuid4().hex[:8]}",
        subdomain=f"{tag}-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )


def _mk_user(tag, role=None, first_name=None):
    u = User.objects.create_user(
        username=f"{tag}-{uuid.uuid4().hex[:8]}@t.test",
        email=f"{tag}-{uuid.uuid4().hex[:8]}@t.test",
        password="Test1234",
        first_name=first_name or tag.capitalize(),
    )
    if role is not None:
        u.role = role
        u.save(update_fields=["role"])
    return u


# ---------------------------------------------------------------------------
# 1. Preference layer is no longer inert
# ---------------------------------------------------------------------------


class DispatchUserPreferenceFallbackTests(TestCase):
    def setUp(self):
        self.school = _mk_school("pref")
        self.user = _mk_user("prefuser", role=User.Role.PARENT)
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role=User.Role.PARENT, is_primary=True
        )
        self.context = {
            "title": "Fees due",
            "message": "Please settle the term balance.",
            "phone": "+237600000001",
            "email": self.user.email,
        }

    def _dispatch(self):
        # Transports are stubbed so a channel that is NOT skipped by preference
        # returns a truthy send -- that is what makes "skipped:pref" meaningful.
        with patch(
            "apps.communication.notification_service.send_sms", return_value=True
        ), patch(
            "apps.communication.notification_service.send_email", return_value=True
        ), patch(
            "apps.communication.consent.is_channel_suppressed", return_value=False
        ):
            return dispatch_event(
                "fee.reminder",
                recipient=self.user,
                context=dict(self.context),
                school=self.school,
            )

    def test_no_preference_row_at_all_leaves_every_channel_open(self):
        """Baseline: absent both preference models, defaults still apply."""
        result = self._dispatch()
        self.assertNotEqual(result["results"]["sms"], "skipped:pref")
        self.assertNotEqual(result["results"]["email"], "skipped:pref")

    def test_unconfigured_user_preference_row_is_not_read_as_mute_everything(self):
        """An auto-created row with an empty channel list means 'never set'."""
        UserPreference.objects.update_or_create(
            user=self.user, defaults={"notification_channels": []}
        )
        result = self._dispatch()
        self.assertNotEqual(result["results"]["sms"], "skipped:pref")
        self.assertNotEqual(result["results"]["email"], "skipped:pref")

    def test_unticking_sms_actually_suppresses_the_sms(self):
        UserPreference.objects.update_or_create(
            user=self.user, defaults={"notification_channels": ["EMAIL", "APP"]}
        )
        result = self._dispatch()
        self.assertEqual(result["results"]["sms"], "skipped:pref")
        # The channels the user kept are untouched -- this is not a blanket mute.
        self.assertNotEqual(result["results"]["email"], "skipped:pref")
        self.assertNotEqual(result["results"]["in_app"], "skipped:pref")

    def test_safeguarding_is_never_suppressed_by_a_channel_choice(self):
        """Child protection must not be silenceable through a preference screen."""
        UserPreference.objects.update_or_create(
            user=self.user, defaults={"notification_channels": ["EMAIL"]}
        )
        with patch(
            "apps.communication.notification_service.send_sms", return_value=True
        ), patch(
            "apps.communication.consent.is_channel_suppressed", return_value=False
        ):
            result = dispatch_event(
                "safeguarding.concern_raised",
                recipient=self.user,
                context=dict(self.context),
                school=self.school,
            )
        self.assertNotEqual(result["results"]["sms"], "skipped:pref")

    def test_get_preference_derives_from_user_preference(self):
        UserPreference.objects.update_or_create(
            user=self.user, defaults={"notification_channels": ["EMAIL"]}
        )
        pref = get_preference(self.user)
        self.assertIsNotNone(pref, "no preference derived from UserPreference")
        self.assertTrue(pref.allows("fees", "email"))
        self.assertFalse(pref.allows("fees", "sms"))

    def test_preference_screen_post_reaches_the_dispatch_router(self):
        """End-to-end: the screen the parent actually uses drives the router."""
        self.client.force_login(self.user)
        url = reverse("accounts:notification_preferences")
        response = self.client.post(url, {"notification_channels": ["EMAIL", "APP"]})
        # Anti-vacuity: prove the POST reached the view body rather than being
        # bounced by auth/MFA -- the row must carry exactly what we submitted.
        pref = UserPreference.objects.filter(user=self.user).first()
        self.assertIsNotNone(pref, f"view never wrote a row (status={response.status_code})")
        self.assertEqual(sorted(pref.notification_channels), ["APP", "EMAIL"])

        result = self._dispatch()
        self.assertEqual(result["results"]["sms"], "skipped:pref")


# ---------------------------------------------------------------------------
# 2. A retried SMS reaches the provider
# ---------------------------------------------------------------------------


class SmsIdempotencyRetryTests(TestCase):
    def setUp(self):
        self.school = _mk_school("sms")
        self.key = f"outbound-{uuid.uuid4().hex[:8]}"
        self.phone = "+237600000002"

    def test_reserve_reclaims_a_failed_row(self):
        SmsSendLog.objects.create(
            idempotency_key=self.key,
            recipient_hash="deadbeef",
            status=SmsSendLog.Status.FAILED,
        )
        reservation = _sms_idempotency_reserve(
            key=self.key, to_phone=self.phone, school=self.school
        )
        self.assertNotEqual(
            reservation, "duplicate", "a FAILED row blocked the retry forever"
        )
        self.assertIsInstance(reservation, SmsSendLog)
        self.assertEqual(reservation.status, SmsSendLog.Status.PENDING)

    def test_reserve_still_dedupes_sent_and_in_flight_rows(self):
        """The double-send guard the reclaim must not weaken."""
        for status in (SmsSendLog.Status.SENT, SmsSendLog.Status.PENDING):
            key = f"{self.key}-{status}"
            SmsSendLog.objects.create(
                idempotency_key=key, recipient_hash="deadbeef", status=status
            )
            self.assertEqual(
                _sms_idempotency_reserve(
                    key=key, to_phone=self.phone, school=self.school
                ),
                "duplicate",
                f"{status} row was not treated as a duplicate",
            )

    @contextmanager
    def _stubbed_provider(self, outcomes):
        """Drive send_sms with a scripted provider outcome per call."""
        router = mock.MagicMock()
        router.route.side_effect = outcomes
        with patch(
            "apps.communication.notification_service._resolve_site_settings",
            return_value=None,
        ), patch(
            "apps.communication.notification_service.circuit_is_open",
            return_value=False,
        ), patch(
            "apps.communication.notification_service.circuit_record_success"
        ), patch(
            "apps.communication.notification_service.circuit_record_failure"
        ), patch(
            "apps.communication.notification_service._bump_sms_usage_meter"
        ), patch(
            "apps.communication.notification_service._record_sms_route_attempts"
        ), patch(
            "apps.communication.notification_service.get_sms_provider",
            return_value=object(),
        ), patch(
            "apps.communication.consent.is_channel_suppressed", return_value=False
        ), patch(
            "apps.communication.sms_router.SMSMultiGatewayRouter"
        ) as router_cls:
            router_cls.for_destination.return_value = router
            yield router

    def test_retry_after_provider_failure_calls_the_provider_again(self):
        failed = SimpleNamespace(ok=False, provider_key="stub", result=None)
        succeeded = SimpleNamespace(
            ok=True,
            provider_key="stub",
            result=SimpleNamespace(provider_message_id="pm-1"),
        )
        with self._stubbed_provider([failed, succeeded]) as router:
            first = send_sms(
                self.phone,
                "Body",
                school=self.school,
                idempotency_key=self.key,
                queue_on_failure=False,
            )
            self.assertFalse(first)
            self.assertEqual(router.route.call_count, 1)
            self.assertEqual(
                SmsSendLog.objects.get(idempotency_key=self.key).status,
                SmsSendLog.Status.FAILED,
            )

            second = send_sms(
                self.phone,
                "Body",
                school=self.school,
                idempotency_key=self.key,
                queue_on_failure=False,
            )

        self.assertEqual(
            router.route.call_count,
            2,
            "the retry was short-circuited as a duplicate; the SMS was never sent",
        )
        self.assertTrue(second)
        self.assertEqual(
            SmsSendLog.objects.get(idempotency_key=self.key).status,
            SmsSendLog.Status.SENT,
        )


# ---------------------------------------------------------------------------
# 3. @mention notifications fire from the real posting path
# ---------------------------------------------------------------------------


@contextmanager
def autocommit_on_commit():
    """Reproduce production's ``on_commit`` timing inside a Django TestCase.

    ``ATOMIC_REQUESTS`` is set nowhere in config/settings.py, so a view runs in
    autocommit and ``transaction.on_commit(cb)`` executes ``cb`` immediately. A
    ``TestCase`` wraps every test in its own atomic block, which silently turns
    that into "deferred forever" and hides any ordering bug -- which is exactly
    why the existing IM-7 test could pass over broken code.

    The shim compares the atomic nesting depth at registration time with the
    depth on entry: same depth means the caller is effectively in autocommit, so
    run now; deeper means the caller opened its own ``atomic()``, so defer to
    that block's commit (approximated as the end of this context).
    """
    baseline = len(connection.savepoint_ids)
    deferred = []

    def _shim(func, using=None, robust=False):
        if len(connection.savepoint_ids) <= baseline:
            func()
        else:
            deferred.append(func)

    with patch("django.db.transaction.on_commit", _shim):
        yield deferred
    for func in deferred:
        func()


class GroupThreadMentionOrderingTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.school = _mk_school("mention")
        self.alice = _mk_user("alice", role=User.Role.TEACHER, first_name="Alice")
        self.bob = _mk_user("bob", role=User.Role.TEACHER, first_name="Bob")
        self.carol = _mk_user("carol", role=User.Role.TEACHER, first_name="Carol")
        for u in (self.alice, self.bob, self.carol):
            SchoolMembership.objects.create(
                user=u, school=self.school, role="TEACHER", is_primary=True
            )
        self.thread = MessageThread.objects.create(
            title="Staff Room",
            scope=MessageThread.Scope.GLOBAL,
            created_by=self.alice,
            school=self.school,
        )
        self.thread.members.add(self.alice, self.bob, self.carol)

    def _post(self, body):
        request = self.rf.post(f"/groups/{self.thread.id}/", {"message": body})
        SessionMiddleware(lambda r: None).process_request(request)
        setattr(request, "_messages", FallbackStorage(request))
        request.user = self.alice
        request.school = self.school
        return views_groups.group_detail(request, self.thread.id)

    def test_mention_notification_fires_from_the_real_posting_path(self):
        # Bob muted the thread: only the mention path can still reach him.
        ThreadMute.objects.create(thread=self.thread, user=self.bob)

        with mock.patch(
            "apps.communication.dispatch.dispatch_event"
        ) as dispatched, autocommit_on_commit():
            response = self._post(f"ping @{self.bob.username}")

        # Anti-vacuity: the POST really went through the message-create branch.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.thread.messages.count(), 1)
        self.assertGreater(dispatched.call_count, 0, "nothing dispatched at all")

        bob_calls = [
            c for c in dispatched.call_args_list
            if c.kwargs.get("recipient") == self.bob
        ]
        self.assertEqual(
            len(bob_calls), 1, "muted-but-mentioned member was not notified"
        )
        self.assertIn("mentioned you", bob_calls[0].kwargs["context"]["title"])

        carol_calls = [
            c for c in dispatched.call_args_list
            if c.kwargs.get("recipient") == self.carol
        ]
        self.assertEqual(len(carol_calls), 1)
        self.assertIn("New message", carol_calls[0].kwargs["context"]["title"])


# ---------------------------------------------------------------------------
# 4. An API-created announcement is actually delivered
# ---------------------------------------------------------------------------


class AnnouncementApiDeliveryTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.school = _mk_school("ann")
        self.admin = _mk_user("annadmin", role=User.Role.ADMIN)
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role=User.Role.ADMIN, is_primary=True
        )

    def test_api_create_fans_the_announcement_out(self):
        from apps.communication.api_views import AnnouncementViewSet

        view = AnnouncementViewSet.as_view({"post": "create"})
        request = self.factory.post(
            "/api/v1/communication/announcements/",
            {
                "title": "Sports day",
                "content": "Bring kit",
                "audience": "all_parents",
            },
            format="json",
        )
        request.school = self.school
        force_authenticate(request, user=self.admin)

        with patch(
            "apps.communication.announcement_delivery.deliver_announcement"
        ) as delivered:
            response = view(request)

        # Anti-vacuity: 201 proves the create body ran (not a 403 tenant/role bounce).
        self.assertEqual(response.status_code, 201, getattr(response, "data", None))
        self.assertTrue(
            Announcement.objects.filter(school=self.school, title="Sports day").exists()
        )
        self.assertEqual(
            delivered.call_count, 1, "published announcement was never fanned out"
        )

    def test_periodic_sweep_rescues_an_immediate_publish_that_never_delivered(self):
        from apps.communication.announcement_delivery import (
            send_due_scheduled_announcements,
        )

        stranded = Announcement.objects.create(
            title="Stranded",
            content="Body",
            audience=Announcement.Audience.ALL,
            status=Announcement.Status.PUBLISHED,
            school=self.school,
            created_by=self.admin,
        )
        historical = Announcement.objects.create(
            title="Historical",
            content="Body",
            audience=Announcement.Audience.ALL,
            status=Announcement.Status.PUBLISHED,
            school=self.school,
            created_by=self.admin,
        )
        # created_at is auto_now_add, so age it with an UPDATE.
        Announcement.objects.filter(pk=historical.pk).update(
            created_at=timezone.now() - timedelta(days=30)
        )

        with patch(
            "apps.communication.announcement_delivery.deliver_announcement",
            return_value={"delivered": True},
        ) as delivered:
            send_due_scheduled_announcements()

        swept = {c.args[0].pk for c in delivered.call_args_list}
        self.assertIn(
            stranded.pk, swept, "an un-delivered immediate publish is never rescued"
        )
        # A backstop, not a replay: ancient undelivered rows must stay untouched.
        self.assertNotIn(historical.pk, swept)
