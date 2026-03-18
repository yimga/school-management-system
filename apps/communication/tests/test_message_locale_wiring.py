"""BR-08: Message.locale_target set on API + services."""

import uuid

from django.test import TestCase

from apps.accounts.models import User
from apps.communication.models import Message
from apps.requests.models import AccessRequest
from apps.requests.services import notify_requester
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import RegionConfig


class MessageLocaleWiringTests(TestCase):
    def test_notify_requester_sets_locale_target(self):
        rcode = f"M{uuid.uuid4().hex[:5].upper()}"
        region = RegionConfig.objects.create(
            code=rcode,
            name="Msg locale",
            default_language="fr",
            timezone="UTC",
            date_format="DD/MM/YYYY",
        )
        school = School.objects.create(
            name="R School",
            slug=f"rs-{uuid.uuid4().hex[:8]}",
            subdomain=f"rs-{uuid.uuid4().hex[:8]}",
            default_region=region,
        )
        requester = User.objects.create_user(
            username=f"rq-{uuid.uuid4().hex[:8]}@t.test", password="x"
        )
        actor = User.objects.create_user(
            username=f"ac-{uuid.uuid4().hex[:8]}@t.test", password="x"
        )
        SchoolMembership.objects.create(
            user=requester, school=school, role="TEACHER", is_primary=True
        )
        ar = AccessRequest.objects.create(
            request_type=AccessRequest.RequestType.OTHER,
            status=AccessRequest.Status.PENDING,
            school=school,
            requester=requester,
        )
        notify_requester(ar, title="T", message="M", created_by=actor)
        msg = Message.objects.filter(recipient=requester).order_by("-id").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.locale_target[:2], "fr")
