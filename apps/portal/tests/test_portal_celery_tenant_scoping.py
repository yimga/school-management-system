"""Portal Celery tasks must enter tenant context before touching tenant tables.

``apps.portal`` is TENANT_APPS-only (config/settings.py), so a plain
``celery -A config worker`` runs on ``public`` where ``portal_kbarticle`` /
``feedback_*`` do not exist. Every beat task that reads a tenant table therefore
has to fan out per school through ``_run_with_tenant_context`` — the platform
convention already used by finance/people/communication.

These tests patch ``apps.schools.rls_context.rls_school`` (imported lazily inside
``_run_with_tenant_context``, so patching the source module takes effect) and
assert the DB work happens *inside* an open tenant scope, once per active school.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import TestCase

from apps.portal.models_forums import (
    CommunityForumCategory,
    CommunityForumReply,
    CommunityForumTopic,
)
from apps.schools.models import School

User = get_user_model()


class _ScopeRecorder:
    """Stand-in for ``rls_school`` that records enter/exit order."""

    def __init__(self):
        self.entered = []
        self.exited = []

    @property
    def depth(self):
        return len(self.entered) - len(self.exited)

    def __call__(self, school_id):
        @contextmanager
        def _cm():
            self.entered.append(str(school_id))
            try:
                yield
            finally:
                self.exited.append(str(school_id))

        return _cm()


class PortalBeatTaskTenantScopingTests(TestCase):
    """The three tenant-table beat tasks fan out per school, in tenant context."""

    def setUp(self):
        # Two extra active schools so a single un-scoped call is distinguishable
        # from a real per-school fan-out. Blank subdomain is unique, so pass one.
        School.objects.create(
            name="Scoping School A",
            slug="scoping-school-a",
            subdomain="scopingschoola",
            is_active=True,
        )
        School.objects.create(
            name="Scoping School B",
            slug="scoping-school-b",
            subdomain="scopingschoolb",
            is_active=True,
        )
        self.active_ids = sorted(
            str(pk)
            for pk in School.objects.filter(is_active=True).values_list("id", flat=True)
        )
        self.assertGreaterEqual(len(self.active_ids), 2, "need >1 active school")

    def _assert_scoped_fanout(self, recorder, work_depths):
        # One tenant scope entered per active school, and every scope closed.
        self.assertEqual(sorted(recorder.entered), self.active_ids)
        self.assertEqual(sorted(recorder.exited), self.active_ids)
        # The DB work ran once per school AND while a scope was open (depth 1).
        # This is what keeps the test non-vacuous: a task that merely looped
        # without entering tenant context would record depth 0.
        self.assertEqual(len(work_depths), len(self.active_ids))
        self.assertEqual(work_depths, [1] * len(self.active_ids))

    def test_reindex_kb_help_embeddings_weekly_runs_per_school_in_tenant_context(self):
        from apps.portal.tasks import reindex_kb_help_embeddings_weekly

        recorder = _ScopeRecorder()
        depths = []

        def _fake_call_command(*args, **kwargs):
            depths.append(recorder.depth)

        with patch("apps.schools.rls_context.rls_school", recorder), patch(
            "django.core.management.call_command", side_effect=_fake_call_command
        ):
            reindex_kb_help_embeddings_weekly()

        self._assert_scoped_fanout(recorder, depths)

    def test_purge_help_telemetry_monthly_runs_per_school_in_tenant_context(self):
        from apps.portal.tasks import purge_help_telemetry_monthly

        recorder = _ScopeRecorder()
        depths = []

        def _fake_call_command(*args, **kwargs):
            depths.append(recorder.depth)

        with patch("apps.schools.rls_context.rls_school", recorder), patch(
            "django.core.management.call_command", side_effect=_fake_call_command
        ):
            purge_help_telemetry_monthly()

        self._assert_scoped_fanout(recorder, depths)

    def test_archive_stale_kb_articles_monthly_runs_per_school_in_tenant_context(self):
        from apps.portal.tasks import archive_stale_kb_articles_monthly

        recorder = _ScopeRecorder()
        depths = []

        def _fake_candidates(*args, **kwargs):
            depths.append(recorder.depth)
            return []

        with patch("apps.schools.rls_context.rls_school", recorder), patch(
            "apps.portal.kb_archive.stale_kb_archive_candidates",
            side_effect=_fake_candidates,
        ), patch(
            "apps.portal.kb_archive.archive_kb_articles", return_value={"archived": 0}
        ):
            archive_stale_kb_articles_monthly()

        self._assert_scoped_fanout(recorder, depths)

    def test_beat_task_failure_is_raised_not_folded_into_an_unread_return_value(self):
        """A wrong-schema ProgrammingError must surface, not become {"ok": False}."""
        from apps.portal.tasks import reindex_kb_help_embeddings_weekly

        with patch("apps.schools.rls_context.rls_school", _ScopeRecorder()), patch(
            "django.core.management.call_command",
            side_effect=DatabaseError('relation "portal_kbarticle" does not exist'),
        ):
            with self.assertRaises(DatabaseError):
                reindex_kb_help_embeddings_weekly()


class ForumReplyNotificationTenantScopingTests(TestCase):
    """The forum-reply email task must carry its tenant across the wire."""

    def setUp(self):
        self.school = School.objects.create(
            name="Forum Scoping School",
            slug="forum-scoping-school",
            subdomain="forumscoping",
            is_active=True,
        )
        self.author = User.objects.create_user(
            username="fs_author", email="fs_author@example.com", password="Test1234"
        )
        self.replier = User.objects.create_user(
            username="fs_replier", email="fs_replier@example.com", password="Test1234"
        )
        cat = CommunityForumCategory.objects.create(
            school=self.school, name="General", slug="fs-general"
        )
        self.topic = CommunityForumTopic.objects.create(
            school=self.school,
            category=cat,
            title="Scoping question",
            slug="fs-scoping-question",
            body="Body",
            author=self.author,
        )
        self.reply = CommunityForumReply.objects.create(
            topic=self.topic, author=self.replier, body="Reply body"
        )

    def test_enqueue_carries_school_id(self):
        from apps.portal.forum_notifications import queue_forum_reply_notifications

        with patch("apps.portal.tasks.notify_forum_reply_task.delay") as mock_delay:
            queue_forum_reply_notifications(self.reply)

        self.assertEqual(mock_delay.call_count, 1, "task was never enqueued")
        args, kwargs = mock_delay.call_args
        self.assertEqual(
            kwargs.get("school_id"),
            self.school.pk,
            f"school identifier missing from Celery payload: args={args} kwargs={kwargs}",
        )

    def test_task_runs_the_send_inside_tenant_context(self):
        from apps.portal.tasks import notify_forum_reply_task

        recorder = _ScopeRecorder()
        depths = []

        def _fake_send(reply_id, **kwargs):
            depths.append(recorder.depth)
            return {"sent": 0, "skipped": 0, "errors": 0}

        with patch("apps.schools.rls_context.rls_school", recorder), patch(
            "apps.portal.forum_notifications.send_forum_reply_notifications",
            side_effect=_fake_send,
        ):
            notify_forum_reply_task(self.reply.pk, school_id=self.school.pk)

        self.assertEqual(recorder.entered, [str(self.school.pk)])
        self.assertEqual(depths, [1], "send ran outside the tenant scope")


class ForumEmailPreferenceFailClosedTests(TestCase):
    """A preferences read that errors must not mail a possibly opted-out user."""

    def test_preference_read_error_fails_closed(self):
        from apps.portal import forum_notifications
        from apps.portal.portal_models import PortalPreferences

        user = User.objects.create_user(
            username="prefs_user", email="prefs_user@example.com", password="Test1234"
        )
        # Sanity: with a healthy (empty) preferences table the user IS mailable,
        # so the assertion below measures the error path, not a blanket False.
        self.assertTrue(forum_notifications._user_wants_forum_email(user))

        broken = MagicMock()
        broken.filter.side_effect = DatabaseError("preferences unavailable")
        with patch.object(PortalPreferences, "objects", broken):
            self.assertFalse(forum_notifications._user_wants_forum_email(user))
