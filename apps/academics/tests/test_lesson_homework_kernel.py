"""Wave S-B (v3.96.1 — 2026-05-26) — Lesson + homework lifecycle tests."""

from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase

from apps.academics.lesson_homework_kernel import (
    ARCHIVED,
    CLOSED,
    DRAFT,
    DUE,
    PUBLISHED,
    InvalidLifecycleTransition,
    LessonPlanBlock,
    advance_homework_stage,
    advance_lesson_stage,
    check_overdue_homeworks,
    create_homework,
    create_lesson_plan,
    per_student_overdue_count,
    store_homework,
    store_lesson_plan,
    store_submission,
    submit_student_work,
)


def _objective_block():
    return LessonPlanBlock(
        block_type="objective",
        title="Students will identify the main idea of a passage.",
        duration_minutes=5,
    )


class LessonPlanCreateTests(SimpleTestCase):

    def test_happy_path(self):
        lesson = create_lesson_plan(
            school_id=1, teacher_user_id=7, classroom_id=11,
            subject="ELA", title="Main idea & supporting details",
            blocks=[_objective_block(), LessonPlanBlock(
                block_type="activity", title="Read-aloud", duration_minutes=10,
            )],
        )
        self.assertEqual(lesson.stage, DRAFT)
        self.assertEqual(lesson.subject, "ELA")
        self.assertIn("Main idea", lesson.title)

    def test_requires_objective_block(self):
        with self.assertRaises(ValueError):
            create_lesson_plan(
                school_id=1, teacher_user_id=7, classroom_id=11,
                subject="ELA", title="Lesson",
                blocks=[LessonPlanBlock(block_type="activity", title="Read")],
            )

    def test_negative_duration_rejected(self):
        with self.assertRaises(ValueError):
            create_lesson_plan(
                school_id=1, teacher_user_id=7, classroom_id=11,
                subject="ELA", title="Lesson",
                blocks=[LessonPlanBlock(
                    block_type="objective", title="X", duration_minutes=-3,
                )],
            )


class LessonPlanLifecycleTests(SimpleTestCase):

    def test_draft_to_published(self):
        lesson = create_lesson_plan(
            school_id=1, teacher_user_id=7, classroom_id=None,
            subject="Math", title="Long division",
            blocks=[_objective_block()],
        )
        new = advance_lesson_stage(
            lesson=lesson, target_stage=PUBLISHED, actor_user_id=7,
        )
        self.assertEqual(new.stage, PUBLISHED)

    def test_invalid_jump_raises(self):
        lesson = create_lesson_plan(
            school_id=1, teacher_user_id=7, classroom_id=None,
            subject="Math", title="Long division",
            blocks=[_objective_block()],
        )
        with self.assertRaises(InvalidLifecycleTransition):
            advance_lesson_stage(
                lesson=lesson, target_stage=CLOSED, actor_user_id=7,
            )

    def test_archived_is_terminal(self):
        lesson = create_lesson_plan(
            school_id=1, teacher_user_id=7, classroom_id=None,
            subject="Math", title="Long division",
            blocks=[_objective_block()],
        )
        lesson = advance_lesson_stage(
            lesson=lesson, target_stage=ARCHIVED, actor_user_id=7,
        )
        with self.assertRaises(InvalidLifecycleTransition):
            advance_lesson_stage(
                lesson=lesson, target_stage=PUBLISHED, actor_user_id=7,
            )


def _homework():
    return create_homework(
        school_id=1, teacher_user_id=7, classroom_id=11,
        subject="Math", title="Practice problems set 3",
        instructions="Complete problems 1-10 from textbook.",
        assigned_student_ids=[1, 2, 3, 1],  # dupe — should dedupe
        due_date=date(2026, 6, 1),
    )


class HomeworkCreateTests(SimpleTestCase):

    def test_happy_path(self):
        hw = _homework()
        self.assertEqual(hw.stage, DRAFT)
        # Dedupe + sort
        self.assertEqual(hw.assigned_student_ids, (1, 2, 3))

    def test_empty_students_rejected(self):
        with self.assertRaises(ValueError):
            create_homework(
                school_id=1, teacher_user_id=7, classroom_id=11,
                subject="Math", title="X",
                instructions="Do it.",
                assigned_student_ids=[],
                due_date=None,
            )

    def test_short_instructions_rejected(self):
        with self.assertRaises(ValueError):
            create_homework(
                school_id=1, teacher_user_id=7, classroom_id=11,
                subject="Math", title="OK",
                instructions="hi",
                assigned_student_ids=[1],
                due_date=None,
            )


class HomeworkSubmissionTests(SimpleTestCase):

    def test_submit_on_time(self):
        hw = _homework()
        hw = advance_homework_stage(homework=hw, target_stage=PUBLISHED, actor_user_id=7)
        sub = submit_student_work(
            homework=hw, student_id=1,
            submission_text="Done.",
            today=date(2026, 5, 30),
        )
        self.assertFalse(sub.late)
        self.assertEqual(sub.homework_id, hw.homework_id)

    def test_submit_after_due_marks_late(self):
        hw = _homework()
        hw = advance_homework_stage(homework=hw, target_stage=PUBLISHED, actor_user_id=7)
        sub = submit_student_work(
            homework=hw, student_id=1,
            today=date(2026, 6, 10),
        )
        self.assertTrue(sub.late)

    def test_unassigned_student_rejected(self):
        hw = _homework()
        hw = advance_homework_stage(homework=hw, target_stage=PUBLISHED, actor_user_id=7)
        with self.assertRaises(ValueError):
            submit_student_work(homework=hw, student_id=999)

    def test_cannot_submit_to_draft(self):
        hw = _homework()
        with self.assertRaises(InvalidLifecycleTransition):
            submit_student_work(homework=hw, student_id=1)


class OverdueAggregatorTests(SimpleTestCase):

    def test_overdue_filtered(self):
        h_open = create_homework(
            school_id=1, teacher_user_id=7, classroom_id=11,
            subject="Math", title="Future task",
            instructions="Do later",
            assigned_student_ids=[1],
            due_date=date(2027, 1, 1),
        )
        h_open = advance_homework_stage(
            homework=h_open, target_stage=PUBLISHED, actor_user_id=7,
        )
        h_late = create_homework(
            school_id=1, teacher_user_id=7, classroom_id=11,
            subject="Math", title="Past due",
            instructions="Was due.",
            assigned_student_ids=[1, 2],
            due_date=date(2026, 1, 1),
        )
        h_late = advance_homework_stage(
            homework=h_late, target_stage=PUBLISHED, actor_user_id=7,
        )
        overdue = check_overdue_homeworks(
            homeworks=[h_open, h_late], today=date(2026, 5, 26),
        )
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0].title, "Past due")

    def test_per_student_overdue_count(self):
        h_late = create_homework(
            school_id=1, teacher_user_id=7, classroom_id=11,
            subject="Math", title="Past due",
            instructions="Was due.",
            assigned_student_ids=[1, 2, 3],
            due_date=date(2026, 1, 1),
        )
        h_late = advance_homework_stage(
            homework=h_late, target_stage=PUBLISHED, actor_user_id=7,
        )
        sub_1 = submit_student_work(homework=h_late, student_id=1, today=date(2026, 1, 1))
        out = per_student_overdue_count(
            homeworks=[h_late], submissions=[sub_1], today=date(2026, 5, 26),
        )
        # Student 1 submitted → not overdue. Students 2 and 3 didn't.
        self.assertEqual(out.get(2, 0), 1)
        self.assertEqual(out.get(3, 0), 1)
        self.assertNotIn(1, out)


class StorageHelperTests(SimpleTestCase):

    def test_store_and_retrieve_lesson(self):
        lesson = create_lesson_plan(
            school_id=1, teacher_user_id=7, classroom_id=None,
            subject="Math", title="Long division",
            blocks=[_objective_block()],
        )
        settings = store_lesson_plan(school_settings={}, lesson=lesson)
        self.assertIn(lesson.lesson_id, settings["academics"]["lesson_plans"])

    def test_store_homework_and_submission(self):
        hw = _homework()
        hw = advance_homework_stage(homework=hw, target_stage=PUBLISHED, actor_user_id=7)
        s = store_homework(school_settings={}, homework=hw)
        sub = submit_student_work(homework=hw, student_id=1, today=date(2026, 5, 26))
        s = store_submission(school_settings=s, submission=sub)
        per_hw = s["academics"]["homework_submissions"][hw.homework_id]
        self.assertIn("1", per_hw)
