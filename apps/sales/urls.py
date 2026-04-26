from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    path("", views.pipeline_board, name="pipeline_board"),
    path("leads/new/", views.lead_create, name="lead_create"),
    path("leads/<int:pk>/", views.lead_detail, name="lead_detail"),
    path("leads/<int:pk>/stage/", views.update_stage, name="update_stage"),
]
