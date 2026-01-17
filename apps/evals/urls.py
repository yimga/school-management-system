from django.urls import path
from .views import teacher_dashboard, teacher_marks_entry, teacher_marks_list

urlpatterns = [
    path("teacher/", teacher_dashboard, name="teacher_dashboard"),
    path("teacher/marks/entry/", teacher_marks_entry, name="teacher_marks_entry"),
    path("teacher/marks/", teacher_marks_list, name="teacher_marks_list"),
]

