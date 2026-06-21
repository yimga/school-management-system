"""Gap-audit tests for the group-thread parity work (IM-4 / IM-5 / IM-6).

Covers, via RequestFactory (so tenant middleware / template rendering don't get
in the way of the unit under test):

  IM-4  read-state-correct unread counts on the Groups landing.
  IM-5  live new-message delivery + live read receipts (group_messages_since),
        attachment upload persistence, and membership-gated attachment download.
  IM-6  edit (author-only, stamps edited_at) + soft-delete (author or moderator).
"""

import json
import uuid

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.communication import views_groups
from apps.communication.models import (
    MessageThread,
    ThreadMessage,
    ThreadMessageAttachment,
    ThreadReadState,
)
from apps.schools.models import School


def _teacher(tag):
    u = User.objects.create_user(
        username=f"{tag}-{uuid.uuid4().hex[:8]}@t.test", password="x"
    )
    u.role = User.Role.TEACHER
    u.save(update_fields=["role"])
    return u


def _attach_request_extras(request, user, school):
    """Wire the bits the views read that middleware would normally supply.

    The session is left unsaved (in-memory) on purpose: the views only use it as
    fallback storage for ``messages``, which never needs the DB here, and writing
    it would add pointless DB churn between direct view calls.
    """
    SessionMiddleware(lambda r: None).process_request(request)
    setattr(request, "_messages", FallbackStorage(request))
    request.user = user
    request.school = school


class GroupThreadParityTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="Parity School",
            slug=f"ps-{uuid.uuid4().hex[:10]}",
            subdomain=f"ps-{uuid.uuid4().hex[:10]}",
        )
        self.other_school = School.objects.create(
            name="Other School",
            slug=f"os-{uuid.uuid4().hex[:10]}",
            subdomain=f"os-{uuid.uuid4().hex[:10]}",
        )
        self.author = _teacher("author")
        self.member = _teacher("member")
        self.outsider = _teacher("outsider")
        self.thread = MessageThread.objects.create(
            title="Grade 5 Staff",
            scope=MessageThread.Scope.GLOBAL,
            created_by=self.author,
            school=self.school,
        )
        self.thread.members.add(self.author, self.member)
        self.m1 = ThreadMessage.objects.create(
            thread=self.thread, author=self.author, content="first"
        )
        self.m2 = ThreadMessage.objects.create(
            thread=self.thread, author=self.author, content="second"
        )

    # ---- IM-4 ---------------------------------------------------------------
    def test_unread_count_is_read_state_correct(self):
        # The member has never opened the thread -> both messages are unread.
        threads = [self.thread]
        views_groups._attach_thread_unread_counts(threads, self.member)
        self.assertEqual(threads[0].unread_count, 2)

        # After the member reads, unread drops to 0.
        ThreadReadState.objects.update_or_create(
            thread=self.thread,
            user=self.member,
            defaults={"last_read_at": self.m2.created_at},
        )
        views_groups._attach_thread_unread_counts(threads, self.member)
        self.assertEqual(threads[0].unread_count, 0)

    # ---- IM-5 live delivery + receipts -------------------------------------
    def test_member_sees_messages_live_and_marks_read(self):
        req = self.rf.get("/x", {"after": "0"})
        _attach_request_extras(req, self.member, self.school)
        resp = views_groups.group_messages_since(req, self.thread.id)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        ids = {m["id"] for m in data["messages"]}
        self.assertEqual(ids, {self.m1.id, self.m2.id})
        # Viewing live stamped the member's read state.
        self.assertTrue(
            ThreadReadState.objects.filter(
                thread=self.thread, user=self.member
            ).exists()
        )

    def test_after_cursor_only_returns_newer(self):
        req = self.rf.get("/x", {"after": str(self.m1.id)})
        _attach_request_extras(req, self.member, self.school)
        data = json.loads(views_groups.group_messages_since(req, self.thread.id).content)
        self.assertEqual([m["id"] for m in data["messages"]], [self.m2.id])

    def test_author_receipts_tick_up_after_member_reads(self):
        # Before anyone reads: author's own-message receipts show read_by 0.
        req_a = self.rf.get("/x", {"after": "999999"})  # no new msgs, just receipts
        _attach_request_extras(req_a, self.author, self.school)
        receipts = json.loads(
            views_groups.group_messages_since(req_a, self.thread.id).content
        )["receipts"]
        by_id = {r["id"]: r for r in receipts}
        self.assertEqual(by_id[self.m1.id]["read_by"], 0)
        self.assertEqual(by_id[self.m1.id]["total"], 1)

        # Member opens the thread (stamps read state).
        req_m = self.rf.get("/x", {"after": "0"})
        _attach_request_extras(req_m, self.member, self.school)
        views_groups.group_messages_since(req_m, self.thread.id)

        # Author polls again: read_by is now 1.
        req_a2 = self.rf.get("/x", {"after": "999999"})
        _attach_request_extras(req_a2, self.author, self.school)
        receipts2 = json.loads(
            views_groups.group_messages_since(req_a2, self.thread.id).content
        )["receipts"]
        by_id2 = {r["id"]: r for r in receipts2}
        self.assertEqual(by_id2[self.m1.id]["read_by"], 1)

    def test_non_member_cannot_poll(self):
        req = self.rf.get("/x", {"after": "0"})
        _attach_request_extras(req, self.outsider, self.school)
        resp = views_groups.group_messages_since(req, self.thread.id)
        self.assertEqual(resp.status_code, 403)

    # ---- IM-5 attachments ---------------------------------------------------
    def test_attachment_persists_and_download_is_membership_gated(self):
        att = ThreadMessageAttachment.objects.create(
            message=self.m1,
            file=SimpleUploadedFile("note.pdf", b"%PDF-1.4 test", "application/pdf"),
            original_name="note.pdf",
            content_type="application/pdf",
            size_bytes=12,
            uploaded_by=self.author,
        )
        # Member may download.
        req_m = self.rf.get("/x")
        _attach_request_extras(req_m, self.member, self.school)
        resp_m = views_groups.group_attachment_download(req_m, att.id)
        self.assertEqual(resp_m.status_code, 200)
        # Close the underlying file handle directly — NOT resp_m.close(), which
        # fires request_finished -> close_old_connections and would drop the
        # test's transaction-wrapped DB connection mid-test.
        fh = getattr(resp_m, "file_to_stream", None)
        if fh:
            fh.close()

        # A non-member from another tenant may not.
        req_o = self.rf.get("/x")
        _attach_request_extras(req_o, self.outsider, self.other_school)
        resp_o = views_groups.group_attachment_download(req_o, att.id)
        self.assertEqual(resp_o.status_code, 403)

    def test_attachment_only_post_creates_message(self):
        req = self.rf.post(
            "/x",
            {
                "message": "",
                "attachments": SimpleUploadedFile(
                    "x.png", b"\x89PNG\r\n\x1a\n", "image/png"
                ),
            },
        )
        _attach_request_extras(req, self.member, self.school)
        before = ThreadMessage.objects.filter(thread=self.thread).count()
        resp = views_groups.group_detail(req, self.thread.id)
        self.assertEqual(resp.status_code, 302)  # redirect after post
        self.assertEqual(
            ThreadMessage.objects.filter(thread=self.thread).count(), before + 1
        )
        newest = (
            ThreadMessage.objects.filter(thread=self.thread, author=self.member)
            .order_by("-id")
            .first()
        )
        self.assertEqual(newest.attachments.count(), 1)

    # ---- IM-6 edit / delete -------------------------------------------------
    def test_author_can_edit_and_it_stamps_edited(self):
        req = self.rf.post("/x", {"message": "first (corrected)"})
        _attach_request_extras(req, self.author, self.school)
        resp = views_groups.group_message_edit(req, self.thread.id, self.m1.id)
        self.assertEqual(resp.status_code, 302)
        self.m1.refresh_from_db()
        self.assertEqual(self.m1.content, "first (corrected)")
        self.assertIsNotNone(self.m1.edited_at)
        self.assertEqual(self.m1.edited_by_id, self.author.id)

    def test_non_author_cannot_edit(self):
        req = self.rf.post("/x", {"message": "hijack"})
        _attach_request_extras(req, self.member, self.school)
        resp = views_groups.group_message_edit(req, self.thread.id, self.m1.id)
        self.assertEqual(resp.status_code, 403)
        self.m1.refresh_from_db()
        self.assertEqual(self.m1.content, "first")

    def test_author_can_soft_delete(self):
        req = self.rf.post("/x", {})
        _attach_request_extras(req, self.author, self.school)
        resp = views_groups.group_message_delete(req, self.thread.id, self.m2.id)
        self.assertEqual(resp.status_code, 302)
        self.m2.refresh_from_db()
        self.assertTrue(self.m2.is_deleted)
        self.assertEqual(self.m2.deleted_by_id, self.author.id)
        # Soft-deleted messages drop out of the live feed.
        req2 = self.rf.get("/x", {"after": "0"})
        _attach_request_extras(req2, self.member, self.school)
        data = json.loads(
            views_groups.group_messages_since(req2, self.thread.id).content
        )
        self.assertNotIn(self.m2.id, {m["id"] for m in data["messages"]})

    def test_moderator_can_delete_others_message(self):
        # The thread creator (author) moderates a message posted by the member.
        member_msg = ThreadMessage.objects.create(
            thread=self.thread, author=self.member, content="from member"
        )
        req = self.rf.post("/x", {})
        _attach_request_extras(req, self.author, self.school)
        resp = views_groups.group_message_delete(
            req, self.thread.id, member_msg.id
        )
        self.assertEqual(resp.status_code, 302)
        member_msg.refresh_from_db()
        self.assertTrue(member_msg.is_deleted)

    def test_outsider_cannot_delete(self):
        req = self.rf.post("/x", {})
        _attach_request_extras(req, self.outsider, self.school)
        resp = views_groups.group_message_delete(req, self.thread.id, self.m1.id)
        self.assertEqual(resp.status_code, 403)
        self.m1.refresh_from_db()
        self.assertFalse(self.m1.is_deleted)
