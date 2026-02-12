from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.communication.models import DirectConversation, Message


class DirectMessagingPermissionTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher_dm",
            password="pass",
            role=User.Role.TEACHER,
        )
        self.principal = User.objects.create_user(
            username="principal_dm",
            password="pass",
            role=User.Role.PRINCIPAL,
        )
        self.parent = User.objects.create_user(
            username="parent_dm",
            password="pass",
            role=User.Role.PARENT,
        )
        self.student = User.objects.create_user(
            username="student_dm",
            password="pass",
            role=User.Role.STUDENT,
        )

    def test_parent_is_redirected_from_direct_compose(self):
        self.client.force_login(self.parent)
        response = self.client.get(reverse("accounts:direct_compose"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("portal:parent_contact_school"), response.url)

    def test_student_cannot_open_direct_compose(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:direct_compose"))
        self.assertEqual(response.status_code, 403)

    def test_principal_can_send_direct_message(self):
        self.client.force_login(self.principal)
        response = self.client.post(
            reverse("accounts:direct_compose"),
            {
                "recipient": str(self.teacher.id),
                "subject": "Check-in",
                "body": "Please update marks by noon.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Message.objects.filter(
                sender=self.principal,
                recipient=self.teacher,
                body="Please update marks by noon.",
            ).exists()
        )

    def test_parent_cannot_open_direct_thread_with_non_staff(self):
        self.client.force_login(self.parent)
        response = self.client.get(reverse("accounts:direct_thread", args=[self.student.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("portal:parent_contact_school"), response.url)

    def test_closed_parent_conversation_blocks_parent_reply(self):
        # Staff opens a direct thread with parent.
        self.client.force_login(self.principal)
        self.client.post(
            reverse("accounts:direct_compose"),
            {
                "recipient": str(self.parent.id),
                "subject": "Finance update",
                "body": "Please upload receipt.",
            },
        )
        # Staff closes the loop.
        close_response = self.client.post(
            reverse("accounts:direct_thread", args=[self.parent.id]),
            {"action": "close"},
        )
        self.assertEqual(close_response.status_code, 302)
        conversation = DirectConversation.get_or_create_for(self.principal, self.parent)
        self.assertIsNotNone(conversation.closed_at)

        count_before = Message.objects.count()
        self.client.force_login(self.parent)
        reply_response = self.client.post(
            reverse("accounts:direct_thread", args=[self.principal.id]),
            {"subject": "Re", "body": "Can you reopen this?"},
        )
        self.assertEqual(reply_response.status_code, 302)
        self.assertEqual(Message.objects.count(), count_before)

    def test_messages_page_does_not_render_toast_usage_docs(self):
        self.client.force_login(self.principal)
        response = self.client.get(reverse("accounts:user_messages"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Reusable Toast Notification System Usage")
        self.assertNotContains(response, "Include this in base templates, then call")
