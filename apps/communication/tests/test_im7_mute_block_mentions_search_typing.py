"""Gap-audit tests for IM-7: mute, block, @mentions, search, typing.

Notification fan-out is verified by patching ``dispatch_event`` and running the
on-commit hooks (``captureOnCommitCallbacks``); endpoints and helpers are driven
directly via RequestFactory / the test client.
"""

import uuid
from unittest import mock

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.accounts import views as account_views
from apps.communication import views_groups
from apps.communication.models import (
    Message,
    MessageBlock,
    MessageThread,
    ThreadMessage,
    ThreadMessageMention,
    ThreadMute,
)
from apps.schools.models import School, SchoolMembership


def _user(tag, first_name=None, is_superuser=False):
    u = User.objects.create_user(
        username=f"{tag}-{uuid.uuid4().hex[:8]}@t.test",
        password="x",
        first_name=first_name or tag.capitalize(),
    )
    u.role = User.Role.TEACHER
    if is_superuser:
        u.is_superuser = True
        u.is_staff = True
    u.save()
    return u


def _attach(request, user, school):
    SessionMiddleware(lambda r: None).process_request(request)
    setattr(request, "_messages", FallbackStorage(request))
    request.user = user
    request.school = school


class IM7Tests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="IM7 School",
            slug=f"im7-{uuid.uuid4().hex[:10]}",
            subdomain=f"im7-{uuid.uuid4().hex[:10]}",
        )
        self.alice = _user("alice", "Alice")
        self.bob = _user("bob", "Bob")
        self.carol = _user("carol", "Carol")
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

    # ---- Mute ---------------------------------------------------------------
    def test_mute_toggle_creates_and_deletes(self):
        req = self.rf.post("/x")
        _attach(req, self.bob, self.school)
        views_groups.group_mute_toggle(req, self.thread.id)
        self.assertTrue(
            ThreadMute.objects.filter(thread=self.thread, user=self.bob).exists()
        )
        req2 = self.rf.post("/x")
        _attach(req2, self.bob, self.school)
        views_groups.group_mute_toggle(req2, self.thread.id)
        self.assertFalse(
            ThreadMute.objects.filter(thread=self.thread, user=self.bob).exists()
        )

    def test_muted_member_excluded_from_fanout(self):
        ThreadMute.objects.create(thread=self.thread, user=self.bob)
        with mock.patch(
            "apps.communication.dispatch.dispatch_event"
        ) as md:
            with self.captureOnCommitCallbacks(execute=True):
                ThreadMessage.objects.create(
                    thread=self.thread, author=self.alice, content="hi team"
                )
        recipients = {c.kwargs.get("recipient") for c in md.call_args_list}
        self.assertIn(self.carol, recipients)  # non-muted notified
        self.assertNotIn(self.bob, recipients)  # muted excluded

    # ---- @mentions ----------------------------------------------------------
    def test_mention_records_member_only(self):
        msg = ThreadMessage.objects.create(
            thread=self.thread, author=self.alice, content="hey @bob and @charlie"
        )
        views_groups._resolve_and_record_mentions(msg, self.thread, self.alice)
        mentioned = set(
            ThreadMessageMention.objects.filter(message=msg).values_list(
                "user_id", flat=True
            )
        )
        self.assertEqual(mentioned, {self.bob.id})  # @charlie is not a member

    def test_mentioned_member_gets_mention_notification_even_if_muted(self):
        ThreadMute.objects.create(thread=self.thread, user=self.bob)  # bob muted
        with mock.patch("apps.communication.dispatch.dispatch_event") as md:
            with self.captureOnCommitCallbacks(execute=True):
                msg = ThreadMessage.objects.create(
                    thread=self.thread, author=self.alice, content="ping @bob"
                )
                views_groups._resolve_and_record_mentions(
                    msg, self.thread, self.alice
                )
        # Bob (muted but mentioned) is notified with a "mentioned you" title.
        bob_calls = [
            c for c in md.call_args_list if c.kwargs.get("recipient") == self.bob
        ]
        self.assertEqual(len(bob_calls), 1)
        self.assertIn("mentioned you", bob_calls[0].kwargs["context"]["title"])
        # Carol (not mentioned, not muted) gets the plain "new message" title.
        carol_calls = [
            c for c in md.call_args_list if c.kwargs.get("recipient") == self.carol
        ]
        self.assertEqual(len(carol_calls), 1)
        self.assertIn("New message", carol_calls[0].kwargs["context"]["title"])

    # ---- Block --------------------------------------------------------------
    def test_is_blocked_between_is_symmetric(self):
        MessageBlock.objects.create(blocker=self.alice, blocked=self.bob)
        self.assertTrue(MessageBlock.is_blocked_between(self.alice.id, self.bob.id))
        self.assertTrue(MessageBlock.is_blocked_between(self.bob.id, self.alice.id))
        self.assertFalse(MessageBlock.is_blocked_between(self.alice.id, self.carol.id))

    def test_block_toggle_creates_and_deletes(self):
        su = _user("root", "Root", is_superuser=True)
        req = self.rf.post("/x")
        _attach(req, su, self.school)
        account_views.direct_block_toggle(req, self.bob.id)
        self.assertTrue(
            MessageBlock.objects.filter(blocker=su, blocked=self.bob).exists()
        )
        req2 = self.rf.post("/x")
        _attach(req2, su, self.school)
        account_views.direct_block_toggle(req2, self.bob.id)
        self.assertFalse(
            MessageBlock.objects.filter(blocker=su, blocked=self.bob).exists()
        )

    def test_blocked_sender_does_not_notify_recipient(self):
        # Bob blocks Alice; Alice's message to Bob must not notify Bob.
        MessageBlock.objects.create(blocker=self.bob, blocked=self.alice)
        with mock.patch("apps.communication.dispatch.dispatch_event") as md:
            with self.captureOnCommitCallbacks(execute=True):
                Message.objects.create(
                    sender=self.alice,
                    recipient=self.bob,
                    subject="hi",
                    body="hello",
                )
        self.assertEqual(md.call_count, 0)

    def test_unblocked_sender_notifies_recipient(self):
        with mock.patch("apps.communication.dispatch.dispatch_event") as md:
            with self.captureOnCommitCallbacks(execute=True):
                Message.objects.create(
                    sender=self.alice,
                    recipient=self.bob,
                    subject="hi",
                    body="hello",
                )
        self.assertEqual(md.call_count, 1)

    # ---- Typing -------------------------------------------------------------
    def test_typing_mark_and_list(self):
        cache.clear()
        req_post = self.rf.post("/x")
        _attach(req_post, self.alice, self.school)
        self.assertEqual(views_groups.group_typing(req_post, self.thread.id).status_code, 200)

        req_get = self.rf.get("/x")
        _attach(req_get, self.bob, self.school)
        import json

        data = json.loads(views_groups.group_typing(req_get, self.thread.id).content)
        names = {t["name"] for t in data["typing"]}
        self.assertIn("Alice", names)  # bob sees alice typing
        # Alice doesn't see herself.
        req_self = self.rf.get("/x")
        _attach(req_self, self.alice, self.school)
        self_data = json.loads(
            views_groups.group_typing(req_self, self.thread.id).content
        )
        self.assertEqual(self_data["typing"], [])

    def test_typing_requires_membership(self):
        outsider = _user("out", "Out")
        SchoolMembership.objects.create(
            user=outsider, school=self.school, role="TEACHER", is_primary=True
        )
        req = self.rf.get("/x")
        _attach(req, outsider, self.school)
        self.assertEqual(
            views_groups.group_typing(req, self.thread.id).status_code, 403
        )

    # ---- Search -------------------------------------------------------------
    def test_message_search_scoped(self):
        # Direct hit + group hit for alice.
        Message.objects.create(
            sender=self.alice, recipient=self.bob, subject="s", body="pizza party friday"
        )
        ThreadMessage.objects.create(
            thread=self.thread, author=self.bob, content="who brings the pizza?"
        )
        from django.urls import reverse

        self.client.force_login(self.alice)
        resp = self.client.get(reverse("accounts:message_search"), {"q": "pizza"})
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", "replace").lower()
        self.assertIn("pizza", body)
