"""Gap-audit tests for IM-8: offline-first group messaging + AI thread assist.

Covers the security-critical paths:
  - the WAL writer for offline group posts (author from socket, membership +
    tenant enforced, content required);
  - the registry/allowlist wiring;
  - the AI summary collector's access scoping (members only) + entitlement gate;
  - summarize_thread failing closed on empty input.
"""

import uuid

from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.communication.models import MessageThread, ThreadMessage
from apps.schools.models import School, SchoolMembership
from apps.wal_stream import writers
from apps.wal_stream.consumers import _ALLOWED_DOMAINS
from apps.wal_stream.writers import _apply_thread_message_create


def _user(tag):
    u = User.objects.create_user(
        username=f"{tag}-{uuid.uuid4().hex[:8]}@t.test",
        password="x",
        first_name=tag.capitalize(),
    )
    u.role = User.Role.TEACHER
    u.save(update_fields=["role"])
    return u


class IM8OfflineGroupTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="IM8 School",
            slug=f"im8-{uuid.uuid4().hex[:10]}",
            subdomain=f"im8-{uuid.uuid4().hex[:10]}",
        )
        self.other_school = School.objects.create(
            name="Other",
            slug=f"oth-{uuid.uuid4().hex[:10]}",
            subdomain=f"oth-{uuid.uuid4().hex[:10]}",
        )
        self.alice = _user("alice")  # member
        self.carol = _user("carol")  # NOT a member
        self.thread = MessageThread.objects.create(
            title="Ops",
            scope=MessageThread.Scope.GLOBAL,
            created_by=self.alice,
            school=self.school,
        )
        self.thread.members.add(self.alice)

    # ---- WAL writer (offline group post) -----------------------------------
    def test_offline_post_creates_message_for_member(self):
        env = {
            "user_id": self.alice.id,
            "school_id": self.school.id,
            "actions": [{"thread_id": self.thread.id, "content": "from the field"}],
        }
        _apply_thread_message_create(env)
        msgs = ThreadMessage.objects.filter(thread=self.thread, is_deleted=False)
        self.assertEqual(msgs.count(), 1)
        m = msgs.first()
        self.assertEqual(m.author_id, self.alice.id)
        self.assertEqual(m.content, "from the field")

    def test_offline_post_dropped_for_non_member(self):
        env = {
            "user_id": self.carol.id,  # not in thread.members
            "school_id": self.school.id,
            "actions": [{"thread_id": self.thread.id, "content": "sneaky"}],
        }
        _apply_thread_message_create(env)
        self.assertEqual(
            ThreadMessage.objects.filter(thread=self.thread).count(), 0
        )

    def test_offline_post_dropped_cross_school(self):
        # Same author + thread, but the bound tenant is a DIFFERENT school.
        env = {
            "user_id": self.alice.id,
            "school_id": self.other_school.id,
            "actions": [{"thread_id": self.thread.id, "content": "wrong tenant"}],
        }
        _apply_thread_message_create(env)
        self.assertEqual(
            ThreadMessage.objects.filter(thread=self.thread).count(), 0
        )

    def test_offline_post_empty_content_skipped(self):
        env = {
            "user_id": self.alice.id,
            "school_id": self.school.id,
            "actions": [{"thread_id": self.thread.id, "content": "   "}],
        }
        _apply_thread_message_create(env)
        self.assertEqual(
            ThreadMessage.objects.filter(thread=self.thread).count(), 0
        )

    def test_no_author_is_a_noop(self):
        env = {"school_id": self.school.id, "actions": [{"thread_id": self.thread.id, "content": "x"}]}
        _apply_thread_message_create(env)  # must not raise
        self.assertEqual(
            ThreadMessage.objects.filter(thread=self.thread).count(), 0
        )

    def test_domain_registered_and_allowlisted(self):
        self.assertIn("thread_message_create", _ALLOWED_DOMAINS)
        self.assertIn("thread_message_create", writers._REGISTRY)
        self.assertIs(
            writers._REGISTRY["thread_message_create"], _apply_thread_message_create
        )


class IM8AiThreadAssistTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="IM8 AI",
            slug=f"im8ai-{uuid.uuid4().hex[:10]}",
            subdomain=f"im8ai-{uuid.uuid4().hex[:10]}",
        )
        self.alice = _user("alice")
        self.carol = _user("carol")
        SchoolMembership.objects.create(
            user=self.alice, school=self.school, role="TEACHER", is_primary=True
        )
        self.thread = MessageThread.objects.create(
            title="Planning",
            scope=MessageThread.Scope.GLOBAL,
            created_by=self.alice,
            school=self.school,
        )
        self.thread.members.add(self.alice)
        ThreadMessage.objects.create(
            thread=self.thread, author=self.alice, content="agenda item one"
        )

    def _req(self, user):
        req = self.rf.post("/x")
        req.user = user
        req.school = self.school
        return req

    def test_collector_returns_messages_for_member(self):
        from apps.portal.views_ai_draft import _collect_thread_for_summary

        req = self._req(self.alice)
        msgs, kind = _collect_thread_for_summary(req, self.school, "group", self.thread.id)
        self.assertEqual(kind, "group conversation")
        self.assertTrue(msgs)
        self.assertIn("agenda item one", [t for _, t in msgs])

    def test_collector_denies_non_member(self):
        from apps.portal.views_ai_draft import _collect_thread_for_summary

        req = self._req(self.carol)  # not a member of the thread
        msgs, kind = _collect_thread_for_summary(req, self.school, "group", self.thread.id)
        self.assertIsNone(msgs)

    def test_summarize_view_requires_entitlement(self):
        # Without the AI_TEACHER_COMMS entitlement the view returns 402 BEFORE any
        # AI call. Patched for determinism (independent of default entitlement state).
        import json
        from unittest import mock

        from apps.portal.views_ai_draft import ai_summarize_thread

        req = self.rf.post(
            "/x",
            data=json.dumps({"scope": "group", "id": self.thread.id}),
            content_type="application/json",
        )
        req.user = self.alice
        req.school = self.school
        with mock.patch(
            "apps.portal.views_ai_draft._entitlement_ok", return_value=False
        ):
            resp = ai_summarize_thread(req)
        self.assertEqual(resp.status_code, 402)

    def test_summarize_view_non_member_is_404(self):
        # Entitled, but the caller is not a member of the thread -> 404 (no leak).
        import json
        from unittest import mock

        from apps.portal.views_ai_draft import ai_summarize_thread

        req = self.rf.post(
            "/x",
            data=json.dumps({"scope": "group", "id": self.thread.id}),
            content_type="application/json",
        )
        req.user = self.carol  # not a member
        req.school = self.school
        with mock.patch(
            "apps.portal.views_ai_draft._entitlement_ok", return_value=True
        ):
            resp = ai_summarize_thread(req)
        self.assertEqual(resp.status_code, 404)

    def test_summarize_service_fails_closed_on_empty(self):
        from services.messaging_ai import summarize_thread

        out, meta = summarize_thread(school=self.school, messages=[])
        self.assertEqual(out, "")
        self.assertTrue(meta.get("skipped"))
