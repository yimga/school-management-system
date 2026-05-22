from django.urls import path

from .views import LifecycleTimelineView

app_name = "lifecycle"

urlpatterns = [
    path(
        "<uuid:school_id>/",
        LifecycleTimelineView.as_view(),
        name="timeline",
    ),
]
