from django.urls import path
from .views import (
    studio_audit_api,
    studio_global_search,
    studio_preview,
    studio_publish_api,
    studio_recommendations_api,
    studio_rollback,
    studio_save_draft_api,
    studio_shell,
    studio_version_history_api,
)

app_name = "studio_os"

urlpatterns = [
    path("", studio_shell, name="shell"),
    path("experience/", studio_shell, {"mode": "experience"}, name="experience"),
    path("automation/", studio_shell, {"mode": "automation"}, name="automation"),
    path("output/", studio_shell, {"mode": "output"}, name="output"),
    path("launch/", studio_shell, {"mode": "launch"}, name="launch"),
    path("control/", studio_shell, {"mode": "control"}, name="control"),
    path("preview/", studio_preview, name="preview"),
    path("publish/", studio_publish_api, name="publish"),
    path("save-draft/", studio_save_draft_api, name="save_draft"),
    path("version-history/", studio_version_history_api, name="version_history"),
    path("search/", studio_global_search, name="global_search"),
    path("recommendations/", studio_recommendations_api, name="recommendations"),
    path("audit/", studio_audit_api, name="audit"),
    path("rollback/", studio_rollback, name="rollback"),
]
