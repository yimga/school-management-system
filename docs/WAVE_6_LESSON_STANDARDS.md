# Wave 6 — Lesson & Standards

| Sub-item | Description | Status |
|----------|-------------|--------|
| W6-1 | Resource attachments to lessons | ✅ |
| W6-2 | Standards tagging | ✅ |
| W6-3 | AI lesson assistant (optional integration) | Documented (roadmap) |
| W6-4 | Teacher wellness (reminder or link) | ✅ |

## W6-1: Resource attachments to lessons

- **LessonPlan** (portal) already had a single `file` (main lesson plan PDF).
- **LessonPlanAttachment** added: FK to LessonPlan, `file`, optional `label`, `created_at`. Multiple attachments per plan.
- **Teacher flow:** Lesson Notes page lists plans; each plan has "Download" (main file) and **Add resource**. "Add resource" goes to a form (file + optional label); on save, redirects back to Lesson Notes. Attachments are listed under each plan.
- **Code:** `apps/portal/models.py` (LessonPlanAttachment), migration `0020_add_lesson_plan_attachment`, `apps/portal/views.py` (teacher_lesson_plan_add_attachment), `apps/portal/forms.py` (LessonPlanAttachmentForm), `templates/teacher/lesson_notes.html`, `templates/teacher/lesson_plan_add_attachment.html`. Admin: LessonPlanAdmin with LessonPlanAttachmentInline.

## W6-2: Standards tagging

- **CurriculumStandard** and **CurriculumNode** (academics) already exist (hierarchy: subject / unit / chapter / topic).
- **CourseSyllabus.curriculum_nodes** added: M2M to CurriculumNode (optional). Admins and syllabus builders can tag a syllabus with curriculum nodes it aligns to.
- **Code:** `apps/academics/models.py` (CourseSyllabus.curriculum_nodes), migration `0036_course_syllabus_curriculum_nodes`. Admin: CourseSyllabusAdmin uses `filter_horizontal = ("curriculum_nodes",)`.
- **Builder / UI:** Syllabus builder can later surface "Tag with standards" using this M2M; for Wave 6, tagging is available in admin.

## W6-3: AI lesson assistant (optional integration)

- **Roadmap:** Optional integration to generate lesson plans or quizzes from standards (e.g. "Generate from standard" in syllabus builder or lesson notes). No backend implemented in Wave 6.
- **Placeholder:** When building this, use CurriculumNode (and optionally CourseSyllabus.builder_data) as input; call external AI or template service; write result into LessonPlan or builder_data. See Standards audit S9 (Lesson planner: AI-generated plans/quizzes from standards).

## W6-4: Teacher wellness

- **Wellness** link added in teacher portal sidebar (HR & Professional Growth section).
- **View:** `portal:teacher_wellness` at `/portal/teacher/wellness/`. Simple page with short wellbeing message and link to Help centre.
- **Code:** `apps/portal/views.py` (teacher_wellness), `templates/teacher/wellness.html`, `templates/partials/portal_sidebar.html`, `apps/portal/urls.py`.

## Code refs

- `apps/portal/models.py` — LessonPlan, LessonPlanAttachment.
- `apps/portal/views.py` — teacher_lesson_notes (prefetch_related attachments), teacher_lesson_plan_add_attachment, teacher_wellness.
- `apps/portal/forms.py` — LessonPlanUploadForm, LessonPlanAttachmentForm.
- `apps/portal/urls.py` — teacher_lesson_notes, teacher_lesson_plan_add_attachment, teacher_wellness.
- `apps/academics/models.py` — CourseSyllabus.curriculum_nodes, CurriculumStandard, CurriculumNode.
- `apps/academics/admin.py` — CourseSyllabusAdmin.filter_horizontal curriculum_nodes.
- `apps/portal/admin.py` — LessonPlanAdmin, LessonPlanAttachmentInline.
