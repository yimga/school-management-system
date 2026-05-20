"""Community forums (batch 1357)."""

from django.contrib.auth import get_user_model
from django.db.models import F
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.portal.models_forums import (
    CommunityForumCategory,
    CommunityForumReply,
    CommunityForumTopic,
)
from apps.schools.models import School

UserModel = get_user_model()


class CommunityForumsModelTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Forum Test School",
            slug="forum-test",
            subdomain="forumtest",
            is_active=True,
        )
        self.user = UserModel.objects.create_user(
            username="forum_user",
            password="Test1234",
        )

    def test_category_topic_reply_flow(self):
        cat = CommunityForumCategory.objects.create(
            school=self.school,
            name="General",
            slug="general",
        )
        topic = CommunityForumTopic.objects.create(
            school=self.school,
            category=cat,
            title="Hello",
            slug="hello",
            body="First post",
            author=self.user,
        )
        CommunityForumReply.objects.create(
            topic=topic,
            author=self.user,
            body="Reply one",
        )
        CommunityForumTopic.objects.filter(pk=topic.pk).update(
            reply_count=F("reply_count") + 1,
            last_activity_at=timezone.now(),
        )
        topic.refresh_from_db()
        self.assertEqual(topic.reply_count, 1)


@override_settings(
    FEATURE_CONTROL_DEFAULTS={
        "portal_features": {"forums": True, "video": False, "documents": False},
    }
)
class CommunityForumsUrlTests(TestCase):
    def test_forum_home_requires_login(self):
        self.assertEqual(
            self.client.get(reverse("portal:forum_home")).status_code,
            302,
        )

    def test_portal_feature_forums_url_resolves(self):
        self.assertIn(
            "/forums/",
            reverse("portal:portal_feature", kwargs={"feature": "forums"}),
        )
