from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.feedback.models import ReleaseNote, RoadmapItem
from apps.feedback.services import generate_you_said_we_did_items, submit_feature_request, visible_roadmap_for_user
from .base import FeedbackTestCase


class RoadmapReleaseNotesTests(FeedbackTestCase):
    def test_roadmap_visibility_is_explicit(self):
        hidden = RoadmapItem.objects.create(
            title="Internal item",
            problem="Sensitive tenant detail",
            tenant_visibility=False,
            public_visibility=False,
        )
        visible = RoadmapItem.objects.create(
            title="Tenant visible item",
            problem="Safe product improvement",
            tenant_visibility=True,
            public_visibility=True,
        )

        rows = list(visible_roadmap_for_user(self.admin, self.school_a))
        self.assertIn(visible, rows)
        self.assertNotIn(hidden, rows)

    def test_declined_roadmap_requires_reason(self):
        item = RoadmapItem(title="Declined item", problem="Not aligned", status=RoadmapItem.Status.DECLINED)
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_you_said_we_did_uses_released_notes(self):
        feature = submit_feature_request(
            school=self.school_a,
            user=self.admin,
            title="Receipt history",
            problem_statement="Parents need downloadable receipt history.",
        )
        note = ReleaseNote.objects.create(
            title="Receipt history shipped",
            summary="We added downloadable payment history.",
            published_at=timezone.now(),
        )
        note.feature_requests.add(feature)
        items = generate_you_said_we_did_items(self.school_a)
        self.assertEqual(items[0]["we_did"], "We added downloadable payment history.")
