from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.student360.dual_identity import build_identity_matrix


class DualIdentityMatrixTests(SimpleTestCase):
    def test_projects_school_and_program_contexts(self):
        student = SimpleNamespace(
            classroom=SimpleNamespace(name="Grade 10"),
            academic_year=SimpleNamespace(name="2026"),
            specialty=SimpleNamespace(name="Science"),
        )
        program = SimpleNamespace(
            pk=9,
            name="Evening Robotics",
            requirements_json={
                "schedule_mode": "evening_coaching",
                "meeting_windows": ["Tue 18:00", "Thu 18:00"],
            },
            transcript_track="VOCATIONAL",
        )
        matrix = build_identity_matrix(
            student,
            degree_enrollments=[
                SimpleNamespace(
                    program=program,
                    is_active=True,
                    start_date="2026-01-05",
                )
            ],
        )
        self.assertEqual([row["identity_type"] for row in matrix], ["school", "program"])
        self.assertEqual(matrix[1]["schedule_mode"], "evening_coaching")
        self.assertEqual(matrix[1]["meeting_windows"], ["Tue 18:00", "Thu 18:00"])

    def test_excludes_inactive_program_contexts(self):
        student = SimpleNamespace(classroom=None, academic_year=None, specialty=None)
        matrix = build_identity_matrix(
            student,
            degree_enrollments=[
                SimpleNamespace(
                    program=SimpleNamespace(name="Old", requirements_json={}),
                    is_active=False,
                )
            ],
        )
        self.assertEqual(matrix, [])
