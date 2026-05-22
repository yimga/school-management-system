"""Help AI governance — parent/student policy enforcement."""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.portal.help_governance import (
    ai_assistant_panel_enabled_for_request,
    is_parent_or_student_user,
    should_redirect_feature_center_for_request,
)

UserModel = get_user_model()


class HelpGovernanceTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_parent_is_parent_or_student(self):
        user = UserModel(username="p1", role=User.Role.PARENT)
        request = self.factory.get("/help/")
        request.user = user
        self.assertTrue(is_parent_or_student_user(request))

    def test_teacher_gets_ai_panel_when_enabled(self):
        user = UserModel(username="t1", role=User.Role.TEACHER, is_staff=False)
        request = self.factory.get("/help/")
        request.user = user
        self.assertFalse(is_parent_or_student_user(request))
        self.assertTrue(ai_assistant_panel_enabled_for_request(request))

    def test_parent_ai_panel_disabled(self):
        user = UserModel(username="p2", role=User.Role.PARENT)
        request = self.factory.get("/help/")
        request.user = user
        self.assertFalse(ai_assistant_panel_enabled_for_request(request))

    def test_parent_feature_center_redirect(self):
        user = UserModel(username="p3", role=User.Role.PARENT)
        request = self.factory.get("/feature-center/")
        request.user = user
        self.assertTrue(should_redirect_feature_center_for_request(request))
