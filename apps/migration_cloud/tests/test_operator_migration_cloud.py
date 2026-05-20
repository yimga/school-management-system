"""Operator migration cloud connector view tests."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory, TestCase

from apps.migration_cloud.views_connectors import MigrationCloudConnectorOperatorView

User = get_user_model()

HOST = "manager.runmycampus.com"


def _attach_session(request):
    middleware = SessionMiddleware(lambda req: None)
    middleware.process_request(request)
    request.session.save()


class OperatorMigrationCloudTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.view = MigrationCloudConnectorOperatorView.as_view()

    def _request(self, user: User, *, host: str = HOST):
        request = self.factory.get(
            "/super/migration/connectors/operator/",
            HTTP_HOST=host,
        )
        request.user = user
        _attach_session(request)
        request.session["mfa_verified"] = True
        request.session.save()
        return request

    def test_operator_dashboard_staff_only(self):
        user = User.objects.create_user(
            username="staff_op",
            password="unused",
            is_staff=True,
            is_superuser=True,
        )
        response = self.view(self._request(user))
        self.assertEqual(response.status_code, 200)

    def test_non_staff_returns_404(self):
        user = User.objects.create_user(
            username="plain_mc_op",
            password="unused",
            is_staff=False,
            is_superuser=False,
        )
        with self.assertRaises(Http404):
            self.view(self._request(user))
