from apps.feedback.models import FeatureRequest, RoadmapItem
from apps.feedback.services import (
    create_roadmap_item_from_request,
    submit_feature_request,
    vote_feature_request,
)
from .base import FeedbackTestCase


class FeatureRequestFlowTests(FeedbackTestCase):
    def test_votes_weight_priority_but_do_not_auto_plan(self):
        feature = submit_feature_request(
            school=self.school_a,
            user=self.teacher,
            title="Faster attendance entry",
            problem_statement="Daily attendance takes too many clicks.",
            affected_roles=["TEACHER"],
            module="attendance",
        )
        vote_feature_request(feature, self.admin, school=self.school_a)
        feature.refresh_from_db()

        self.assertEqual(feature.vote_count, 1)
        self.assertGreater(feature.weighted_score, 0)
        self.assertEqual(feature.status, FeatureRequest.Status.SUBMITTED)
        self.assertEqual(RoadmapItem.objects.count(), 0)

    def test_operator_can_create_roadmap_item_from_request(self):
        feature = submit_feature_request(
            school=self.school_a,
            user=self.admin,
            title="Payment provider request",
            problem_statement="School needs a regional payment provider.",
            module="finance",
            impact=FeatureRequest.Impact.BLOCKING,
        )
        item = create_roadmap_item_from_request(feature, actor=self.operator)
        feature.refresh_from_db()

        self.assertEqual(item.target_module, "finance")
        self.assertEqual(feature.status, FeatureRequest.Status.UNDER_REVIEW)
        self.assertEqual(item.feature_requests.count(), 1)
