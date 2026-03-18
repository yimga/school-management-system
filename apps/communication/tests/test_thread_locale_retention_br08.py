"""BR-08 locale_target on thread messages + retention command."""

from datetime import timedelta
import uuid

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.communication.comms_locale import locale_target_for_user
from apps.communication.models import MessageThread, ThreadMessage
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import RegionConfig


class ThreadLocaleRetentionTests(TestCase):
    def test_locale_target_set_from_region(self):
        region, _ = RegionConfig.objects.get_or_create(
            code="GBR",
            defaults={
                "name": "UK",
                "default_language": "en-gb",
                "timezone": "Europe/London",
                "date_format": "DD/MM/YYYY",
            },
        )
        school = School.objects.create(
            name="Msg School",
            slug=f"ms-{uuid.uuid4().hex[:10]}",
            subdomain=f"ms-{uuid.uuid4().hex[:10]}",
            default_region=region,
        )
        u = User.objects.create_user(
            username=f"u-{uuid.uuid4().hex[:8]}@t.test",
            password="x",
        )
        thread = MessageThread.objects.create(
            title="T",
            scope=MessageThread.Scope.GLOBAL,
            created_by=u,
            school=school,
        )
        thread.members.add(u)
        msg = ThreadMessage.objects.create(
            thread=thread, author=u, content="hello", locale_target="en-gb"
        )
        self.assertEqual(msg.locale_target[:6], "en-gb"[:6])

    def test_purge_retention_soft_deletes(self):
        school = School.objects.create(
            name="Old Msg",
            slug=f"om-{uuid.uuid4().hex[:10]}",
            subdomain=f"om-{uuid.uuid4().hex[:10]}",
            settings={"comms_thread_retention_days": 1},
        )
        u = User.objects.create_user(
            username=f"v-{uuid.uuid4().hex[:8]}@t.test", password="x"
        )
        thread = MessageThread.objects.create(
            title="Old",
            scope=MessageThread.Scope.GLOBAL,
            created_by=u,
            school=school,
        )
        msg = ThreadMessage.objects.create(thread=thread, author=u, content="x")
        ThreadMessage.objects.filter(pk=msg.pk).update(
            created_at=timezone.now() - timedelta(days=30)
        )
        call_command("purge_thread_message_retention", school_id=school.id)
        msg.refresh_from_db()
        self.assertTrue(msg.is_deleted)

    def test_locale_target_for_user_uses_school_region(self):
        rcode = f"T{uuid.uuid4().hex[:5].upper()}"
        region = RegionConfig.objects.create(
            code=rcode,
            name="Audit region",
            default_language="sw",
            timezone="Africa/Nairobi",
            date_format="DD/MM/YYYY",
        )
        school = School.objects.create(
            name="Loc School",
            slug=f"ls-{uuid.uuid4().hex[:10]}",
            subdomain=f"ls-{uuid.uuid4().hex[:10]}",
            default_region=region,
        )
        u = User.objects.create_user(
            username=f"loc-{uuid.uuid4().hex[:8]}@t.test", password="x"
        )
        SchoolMembership.objects.create(
            user=u, school=school, role="PARENT", is_primary=True
        )
        self.assertEqual(locale_target_for_user(u)[:2], "sw")
