"""Replacement coverage for video conferencing runtime contracts without model migrations."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.communication.video_conferencing import VideoConferenceProvider, VideoConferenceService


class VideoConferencingRuntimeContractTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(
            username="vc-host",
            email="vc-host@example.com",
            password="x",
        )
        self.start_time = timezone.now() + timedelta(hours=1)

    def test_jitsi_create_meeting_returns_required_shape(self):
        service = VideoConferenceService(VideoConferenceProvider.JITSI)
        payload = service.create_meeting(
            host=self.host,
            title="Science Class",
            start_time=self.start_time,
            duration_minutes=45,
        )
        self.assertIn("meeting_id", payload)
        self.assertIn("join_url", payload)
        self.assertIn("host_url", payload)
        self.assertIn("password", payload)
        self.assertTrue(payload["join_url"].startswith("https://"))

    def test_google_meet_create_meeting_returns_required_shape(self):
        service = VideoConferenceService(VideoConferenceProvider.GOOGLE_MEET)
        payload = service.create_meeting(
            host=self.host,
            title="Math Class",
            start_time=self.start_time,
            duration_minutes=60,
        )
        self.assertIn("meeting_id", payload)
        self.assertIn("join_url", payload)
        self.assertIn("host_url", payload)

