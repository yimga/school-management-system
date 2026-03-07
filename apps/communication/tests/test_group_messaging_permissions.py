from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.communication.models import MessageThread, ThreadMessage


class GroupMessagingPermissionTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher_group",
            password="pass",
            role=User.Role.TEACHER,
        )
        self.principal = User.objects.create_user(
            username="principal_group",
            password="pass",
            role=User.Role.PRINCIPAL,
        )
        self.parent = User.objects.create_user(
            username="parent_group",
            password="pass",
            role=User.Role.PARENT,
        )

        self.thread = MessageThread.objects.create(
            title="Staff Coordination",
            description="Weekly updates",
            scope=MessageThread.Scope.GLOBAL,
            created_by=self.teacher,
        )
        self.thread.members.add(self.teacher)

    def test_principal_can_open_group_list(self):
        self.client.force_login(self.principal)
        response = self.client.get(reverse("communication:group_list"))
        self.assertEqual(response.status_code, 200)

    def test_parent_cannot_open_group_list(self):
        self.client.force_login(self.parent)
        response = self.client.get(reverse("communication:group_list"))
        self.assertEqual(response.status_code, 403)

    def test_non_member_cannot_post_to_group(self):
        self.client.force_login(self.principal)
        response = self.client.post(
            reverse("communication:group_detail", args=[self.thread.id]),
            {"message": "Posting without membership"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            ThreadMessage.objects.filter(
                thread=self.thread,
                author=self.principal,
                content="Posting without membership",
            ).exists()
        )

    def test_allowed_role_can_join_then_post(self):
        self.client.force_login(self.principal)
        join_response = self.client.get(reverse("communication:group_join", args=[self.thread.id]))
        self.assertEqual(join_response.status_code, 302)
        self.assertTrue(self.thread.members.filter(id=self.principal.id).exists())

        post_response = self.client.post(
            reverse("communication:group_detail", args=[self.thread.id]),
            {"message": "Joined and posted"},
        )
        self.assertEqual(post_response.status_code, 302)
        self.assertTrue(
            ThreadMessage.objects.filter(
                thread=self.thread,
                author=self.principal,
                content="Joined and posted",
            ).exists()
        )

    def test_member_can_post_message(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("communication:group_detail", args=[self.thread.id]),
            {"message": "Teacher update"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ThreadMessage.objects.filter(
                thread=self.thread,
                author=self.teacher,
                content="Teacher update",
            ).exists()
        )
