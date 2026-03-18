from django.urls import path

from apps.school_events import views


app_name = "school_events"


urlpatterns = [
    path("", views.event_hub, name="event_hub"),
    path("<slug:slug>/", views.event_detail, name="event_detail"),
    path("<slug:slug>/register/", views.register_for_event, name="register_for_event"),
]
