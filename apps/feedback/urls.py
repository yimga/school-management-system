from django.urls import path

from . import views

app_name = "feedback"

urlpatterns = [
    path("feedback/", views.school_feedback_center, name="school_feedback"),
    path("school/feedback/", views.school_feedback_center, name="school_feedback_alias"),
    path("teacher/feedback/", views.role_feedback_center, {"role": "teacher"}, name="teacher_feedback"),
    path("parent/feedback/", views.role_feedback_center, {"role": "parent"}, name="parent_feedback"),
    path("student/feedback/", views.role_feedback_center, {"role": "student"}, name="student_feedback"),
    path("school/roadmap/", views.school_roadmap, name="school_roadmap"),
    path("feature/<int:pk>/vote/", views.vote_feature, name="vote_feature"),
    path("contextual/", views.contextual_feedback, name="contextual"),
    path("pulse/", views.pulse_survey, name="pulse"),
    path("super/voice-of-customer/", views.voice_of_customer, name="voice_of_customer"),
    path("super/product-feedback/", views.voice_of_customer, name="product_feedback"),
    path("super/product-roadmap/", views.product_roadmap, name="product_roadmap"),
    path("super/feedback/<int:pk>/action/", views.operator_feedback_action, name="operator_feedback_action"),
    path("super/feature/<int:pk>/roadmap/", views.add_to_roadmap, name="add_to_roadmap"),
]
