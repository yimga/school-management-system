from django.urls import path

from .views import (
    academic_rules,
    backend_dashboard,
    backend_entity_import,
    backend_entity_console,
    claim_invite,
    clone_year_setup,
    direct_compose,
    direct_thread,
    login_view,
    logout_view,
    redirect_view,
    rbac_dashboard,
    rollover_year,
    user_documentation,
    user_messages,
    user_notifications,
    user_profile,
    workflow_center,
)
from .views_certification import (
    certification_home,
    certification_session_detail,
    certification_export_zip,
    certification_bulk_add_candidates,
    certification_session_override,
)
from .views_mfa import mfa_setup, mfa_verify

try:
    from apps.people.views_backend import (
        backend_student_list,
        backend_student_create,
        backend_teacher_list,
        backend_teacher_create,
        backend_classroom_create,
    )
    BACKEND_PEOPLE_AVAILABLE = True
except ImportError:
    BACKEND_PEOPLE_AVAILABLE = False
    backend_student_list = backend_student_create = None
    backend_teacher_list = backend_teacher_create = backend_classroom_create = None

app_name = "accounts"

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("redirect/", redirect_view, name="redirect"),
    path("profile/", user_profile, name="user_profile"),
    path("notifications/", user_notifications, name="user_notifications"),
    path("messages/", user_messages, name="user_messages"),
    path("messages/direct/compose/", direct_compose, name="direct_compose"),
    path("messages/direct/<int:user_id>/", direct_thread, name="direct_thread"),
    path("documentation/", user_documentation, name="user_documentation"),
    path("rbac/", rbac_dashboard, name="rbac"),
    path("backend/", backend_dashboard, name="backend_dashboard"),
    path("backend-dashboard/", backend_dashboard, name="backend_dashboard_alt"),
    path("backend/import/", backend_entity_import, name="backend_entity_import"),
    path("backend/entities/", backend_entity_console, name="backend_entity_console"),
    path("workflow/", workflow_center, name="workflow_center"),
    path("workflow/clone-year/", clone_year_setup, name="clone_year_setup"),
    path("workflow/rollover/", rollover_year, name="rollover_year"),
    path("workflow/academic-rules/", academic_rules, name="academic_rules"),
    path("certification/", certification_home, name="certification_home"),
    path("certification/session/<int:session_id>/", certification_session_detail, name="certification_session_detail"),
    path("certification/session/<int:session_id>/export.zip", certification_export_zip, name="certification_export_zip"),
    path("certification/session/<int:session_id>/bulk-add/", certification_bulk_add_candidates, name="certification_bulk_add_candidates"),
    path("certification/session/<int:session_id>/override/", certification_session_override, name="certification_session_override"),
    path("claim-invite/", claim_invite, name="claim_invite"),
    path("mfa/setup/", mfa_setup, name="mfa_setup"),
    path("mfa/verify/", mfa_verify, name="mfa_verify"),
    
    # Backend UI for People Management
    path("backend/students/", backend_student_list, name="backend_student_list") if BACKEND_PEOPLE_AVAILABLE else None,
    path("backend/students/create/", backend_student_create, name="backend_student_create") if BACKEND_PEOPLE_AVAILABLE else None,
    path("backend/teachers/", backend_teacher_list, name="backend_teacher_list") if BACKEND_PEOPLE_AVAILABLE else None,
    path("backend/teachers/create/", backend_teacher_create, name="backend_teacher_create") if BACKEND_PEOPLE_AVAILABLE else None,
    path("backend/classrooms/create/", backend_classroom_create, name="backend_classroom_create") if BACKEND_PEOPLE_AVAILABLE else None,
]
# Filter out None values
urlpatterns = [p for p in urlpatterns if p is not None]
