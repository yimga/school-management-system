"""Permission and audience filtering for AI Center."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase

from services.ai_center.constants import FEATURE_CODESPACE_DISCONNECT_PREFIX
from services.ai_center.query_service import answer_platform_question

User = get_user_model()


class AICenterPermissionFilteringTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username=f"tenant_{uuid.uuid4().hex[:8]}",
            password="Test1234!",
            role=User.Role.TEACHER,
        )

    def test_tenant_audience_blocks_super_route(self):
        result = answer_platform_question(
            user=self.user,
            tenant=None,
            role=self.user.role,
            route_context="/super/migration/",
            question="How does migration cloud work?",
            audience="tenant",
        )
        self.assertTrue(result.feature_absent)
        self.assertTrue(result.answer.startswith(FEATURE_CODESPACE_DISCONNECT_PREFIX))

    def test_nonexistent_feature_disconnect(self):
        result = answer_platform_question(
            user=self.user,
            tenant=None,
            role=self.user.role,
            route_context="/",
            question="configure zzzznonexistent_module_xyz settings",
            audience="tenant",
        )
        self.assertTrue(result.feature_absent)

    def test_missing_kb_data_defaulter(self):
        import services.ai_center.indexing as idx_mod

        idx_mod._INDEX_CACHE = []
        result = answer_platform_question(
            user=self.user,
            tenant=None,
            role=self.user.role,
            route_context="/unknown-page/",
            question="What is the exact pixel width of the legacy widget?",
            audience="tenant",
        )
        self.assertTrue(result.missing_context or "DATA DEFAULTER" in result.answer)
