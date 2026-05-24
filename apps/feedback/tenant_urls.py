from django.urls import path

from . import views, views_public_status

app_name = "feedback"

urlpatterns = [
    # rbac-allow: public platform status page (no PII; strategic move v3.27)
    path("status/", views_public_status.public_status_page, name="public_status"),
    # rbac-allow: public status JSON for status.runmycampus.com monitors
    path("status/api/", views_public_status.public_status_json, name="public_status_json"),
    path("feedback/", views.school_feedback_center, name="school_feedback"),
    path("school/feedback/", views.school_feedback_center, name="school_feedback_alias"),
    path("teacher/feedback/", views.role_feedback_center, {"role": "teacher"}, name="teacher_feedback"),
    path("parent/feedback/", views.role_feedback_center, {"role": "parent"}, name="parent_feedback"),
    path("student/feedback/", views.role_feedback_center, {"role": "student"}, name="student_feedback"),
    path("school/roadmap/", views.school_roadmap, name="school_roadmap"),
    path("feature-center/", views.feature_center, name="feature_center"),
    path("school/feature-center/", views.feature_center, name="school_feature_center"),
    path("contact-us/", views.contact_us, name="contact_us"),
    path("school/contact-us/", views.contact_us, name="school_contact_us"),
    path("feature/<int:pk>/vote/", views.vote_feature, name="vote_feature"),
    path("contextual/", views.contextual_feedback, name="contextual"),
    path("pulse/", views.pulse_survey, name="pulse"),
    path("help/", views.help_center, name="help_center"),
    path("release-notes/", views.release_notes_public, name="release_notes_public"),
]
