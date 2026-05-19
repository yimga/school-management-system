
from apps.feedback.models import FeedbackSubmission
from apps.feedback.services import submit_feedback, visible_feedback_for_user
from .base import FeedbackTestCase


class ParentStudentFeedbackPrivacyTests(FeedbackTestCase):
    def test_student_feedback_forces_school_private_and_moderation(self):
        feedback = submit_feedback(
            school=self.school_a,
            user=self.student,
            title="Login not working",
            description="I cannot open my account.",
            privacy_level=FeedbackSubmission.PrivacyLevel.PUBLIC_CANDIDATE,
        )
        self.assertEqual(feedback.privacy_level, FeedbackSubmission.PrivacyLevel.SCHOOL_PRIVATE)
        self.assertTrue(feedback.moderation_required)

    def test_parent_student_only_see_their_own_feedback(self):
        student_feedback = submit_feedback(
            school=self.school_a,
            user=self.student,
            title="Student item",
            description="Student private item.",
        )
        submit_feedback(
            school=self.school_a,
            user=self.parent,
            title="Parent item",
            description="Parent private item.",
        )

        visible = visible_feedback_for_user(self.student, self.school_a)
        self.assertEqual(list(visible), [student_feedback])
