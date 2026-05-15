from apps.feedback.models import FeatureRequest
from apps.feedback.services import submit_feature_request, vote_feature_request
from .base import FeedbackTestCase


class FeedbackPriorityScoringTests(FeedbackTestCase):
    def test_priority_score_uses_more_than_votes(self):
        low = submit_feature_request(
            school=self.school_a,
            user=self.teacher,
            title="Nice color toggle",
            problem_statement="A cosmetic preference.",
            impact=FeatureRequest.Impact.LOW,
            urgency=FeatureRequest.Urgency.SOMEDAY,
        )
        blocking = submit_feature_request(
            school=self.school_a,
            user=self.admin,
            title="Import blocker",
            problem_statement="Imports block onboarding.",
            module="imports",
            impact=FeatureRequest.Impact.BLOCKING,
            urgency=FeatureRequest.Urgency.IMMEDIATE,
            affected_roles=["ADMIN", "BURSAR", "REGISTRAR"],
        )
        vote_feature_request(low, self.admin, school=self.school_a)
        low.refresh_from_db()
        blocking.refresh_from_db()

        self.assertGreater(blocking.weighted_score, low.weighted_score)
