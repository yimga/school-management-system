"""Help center batch 1360 — forum notifications, marketing KB categories, compose AI."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.portal.forum_notifications import (
    forum_reply_recipient_ids,
    send_forum_reply_notifications,
)
from apps.portal.help_forum_compose import forum_compose_assistant_for_request
from apps.portal.models_forums import (
    CommunityForumCategory,
    CommunityForumReply,
    CommunityForumTopic,
)
from apps.schools.models import School

User = get_user_model()


class HelpForumComposeAssistantTests(SimpleTestCase):
    def test_new_topic_path_enables_assistant(self):
        from django.test import RequestFactory

        req = RequestFactory().get("/portal/forums/new/")
        req.user = type("U", (), {"is_authenticated": True})()
        ctx = forum_compose_assistant_for_request(req)
        self.assertTrue(ctx.get("show_forum_compose_assistant"))
        self.assertEqual(ctx.get("forum_compose_mode"), "new_topic")

    def test_anonymous_disabled(self):
        from django.test import RequestFactory

        req = RequestFactory().get("/portal/forums/new/")
        req.user = type("U", (), {"is_authenticated": False})()
        self.assertEqual(forum_compose_assistant_for_request(req), {})


class ForumReplyNotificationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Notify School",
            slug="notify-school",
            subdomain="notifyschool",
            is_active=True,
        )
        self.author = User.objects.create_user(
            username="topic_author",
            email="author@example.com",
            password="Test1234",
        )
        self.replier = User.objects.create_user(
            username="replier",
            email="replier@example.com",
            password="Test1234",
        )
        self.watcher = User.objects.create_user(
            username="watcher",
            email="watcher@example.com",
            password="Test1234",
        )
        cat = CommunityForumCategory.objects.create(
            school=self.school, name="General", slug="general"
        )
        self.topic = CommunityForumTopic.objects.create(
            school=self.school,
            category=cat,
            title="Fees question",
            slug="fees-question",
            body="How do I pay?",
            author=self.author,
        )
        CommunityForumReply.objects.create(
            topic=self.topic, author=self.watcher, body="Following"
        )

    def test_recipient_ids_exclude_replier_include_author_and_watcher(self):
        reply = CommunityForumReply.objects.create(
            topic=self.topic, author=self.replier, body="Try portal wallet"
        )
        ids = forum_reply_recipient_ids(reply)
        self.assertIn(self.author.pk, ids)
        self.assertIn(self.watcher.pk, ids)
        self.assertNotIn(self.replier.pk, ids)

    @patch("apps.portal.forum_notifications.send_mail")
    def test_send_notifications_delivers_to_followers(self, mock_send):
        reply = CommunityForumReply.objects.create(
            topic=self.topic, author=self.replier, body="Answer here"
        )
        result = send_forum_reply_notifications(
            reply.pk, topic_url="https://school.example/portal/forums/topic/1/"
        )
        self.assertGreaterEqual(result["sent"], 1)
        self.assertGreaterEqual(mock_send.call_count, 1)
