from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.portal.views_support import support_ticket_detail
from apps.schools.models import School
from apps.siteconfig.models_feature_controls import GlobalSupportTicket


def _session_request(rf, user, school, path, method="get", data=None):
    if method == "post":
        req = rf.post(path, data=data or {})
    else:
        req = rf.get(path)
    req.user = user
    req.school = school
    SessionMiddleware(lambda r: HttpResponse()).process_request(req)
    req.session.save()
    setattr(req, "_messages", FallbackStorage(req))
    return req


class SupportTicketPortalDetailTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Portal Ticket School",
            slug="portal-ticket-school",
            subdomain="portal-ticket-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="ticket-owner",
            password="pass",
            role=User.Role.ADMIN,
            email="owner@example.com",
        )
        self.ticket = GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.user,
            subject="[Support] Login",
            body="Help me login",
            status=GlobalSupportTicket.Status.RESOLVED,
        )

    def test_detail_renders_and_csat_form_when_resolved(self):
        url = reverse("portal:support_ticket_detail", kwargs={"ticket_id": self.ticket.pk})
        request = _session_request(self.factory, self.user, self.school, url)
        response = support_ticket_detail(request, ticket_id=self.ticket.pk)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "How did we do")
        content = response.content.decode()
        self.assertIn('data-page-archetype="support-ticket"', content)
        self.assertIn('data-sms-offline-read-cache-key="portal_support_ticket"', content)
        self.assertIn('id="support-ticket-heading"', content)

    def test_csat_post_persists(self):
        url = reverse("portal:support_ticket_detail", kwargs={"ticket_id": self.ticket.pk})
        request = _session_request(
            self.factory,
            self.user,
            self.school,
            url,
            method="post",
            data={"action": "csat", "csat_score": "5", "csat_comment": "Great"},
        )
        support_ticket_detail(request, ticket_id=self.ticket.pk)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.csat_score, 5)
        self.assertIn("Great", self.ticket.csat_comment)
