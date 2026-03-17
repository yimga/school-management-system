from django.shortcuts import redirect
from django.urls import path, reverse, reverse_lazy
from django.contrib.auth.views import PasswordChangeDoneView

from .views import (
    auth_root_redirect,
    request_waiver,
    backend_ops_watch_data,
    backend_entity_import,
    backend_entity_console,
    claim_invite,
    direct_compose,
    direct_thread,
    login_view,
    logout_view,
    PasswordChangeView,
    profile_edit,
    redirect_view,
    rbac_dashboard,
    school_picker,
    switch_portal_role,
    user_documentation,
    user_messages,
    user_notifications,
    user_profile,
)
from .views_migration import (
    migration_run_list,
    migration_rollback,
    migration_legacy_view,
    legacy_data_cleaner_view,
    migration_wizard,
)
from .views_rollover import (
    clone_year_setup,
    rollover_year,
    rollover_queue,
    rollover_proposal_detail,
    rollover_prepare,
)
from .views_workflow import (
    academic_rules,
    automation_hub,
)
from .views_dashboard import backend_dashboard, backend_dashboard_status_fragment
from .views_onboarding import dismiss_first_login_checklist, mark_tour_complete
from .views_delegation import (
    my_delegations,
    delegation_add,
    delegation_edit,
    delegation_revoke,
    delegation_catch_up,
)
from .views_certification import (
    certification_home,
    certification_session_detail,
    certification_export_zip,
    certification_bulk_add_candidates,
    certification_session_override,
)
from .views_mfa import mfa_setup, mfa_verify, dismiss_mfa_banner
from .views_passkey import (
    passkey_registration_options,
    passkey_registration_verify,
    passkey_authentication_options,
    passkey_authentication_verify,
)
from .views_security import (
    api_security_strength,
    api_security_activity,
    api_security_export_log,
    api_security_lockdown,
    sessions_page,
    sessions_revoke,
)
from .views_oidc import oidc_start, oidc_callback
from .views_saml import saml_start, saml_acs, saml_metadata
from .views_impersonation import impersonate_entry, end_impersonation

try:
    from apps.people.views_backend import (
        backend_student_list,
        backend_student_create,
        backend_teacher_list,
        backend_teacher_create,
        backend_classroom_list,
        backend_classroom_create,
        backend_guardian_list,
        backend_applicant_list,
        backend_applicant_create,
        alumni_list,
    )
    BACKEND_PEOPLE_AVAILABLE = True
except ImportError:
    BACKEND_PEOPLE_AVAILABLE = False
    backend_student_list = backend_student_create = alumni_list = None
    backend_teacher_list = backend_teacher_create = backend_classroom_list = backend_classroom_create = backend_guardian_list = backend_applicant_list = None

app_name = "accounts"

urlpatterns = [
    path("", auth_root_redirect, name="root"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("impersonate/", impersonate_entry, name="impersonate_entry"),
    path("end-impersonation/", end_impersonation, name="end_impersonation"),
    path("school-picker/", school_picker, name="school_picker"),
    path("redirect/", redirect_view, name="redirect"),
    path("switch-portal-role/", switch_portal_role, name="switch_portal_role"),
    path("profile/", user_profile, name="user_profile"),
    path("profile/edit/", profile_edit, name="profile_edit"),
    path("profile/delegations/", my_delegations, name="my_delegations"),
    path("profile/delegations/add/", delegation_add, name="delegation_add"),
    path("profile/delegations/<int:pk>/edit/", delegation_edit, name="delegation_edit"),
    path("profile/delegations/<int:pk>/revoke/", delegation_revoke, name="delegation_revoke"),
    path("profile/delegations/catch-up/", delegation_catch_up, name="delegation_catch_up"),
    path("profile/password/", PasswordChangeView.as_view(
        template_name="accounts/password_change_form.html",
        success_url=reverse_lazy("accounts:password_change_done"),
    ), name="password_change"),
    path("profile/password/done/", PasswordChangeDoneView.as_view(
        template_name="accounts/password_change_done.html",
    ), name="password_change_done"),
    path("notifications/", user_notifications, name="user_notifications"),
    path("messages/", user_messages, name="user_messages"),
    path("messages/direct/compose/", direct_compose, name="direct_compose"),
    path("messages/direct/<int:user_id>/", direct_thread, name="direct_thread"),
    path("documentation/", user_documentation, name="user_documentation"),
    path("rbac/", rbac_dashboard, name="rbac"),
    path("backend/", backend_dashboard, name="backend_dashboard"),
    path("backend/request-waiver/", request_waiver, name="request_waiver"),
    path("backend/status/fragment/", backend_dashboard_status_fragment, name="backend_dashboard_status_fragment"),
    path("backend/dismiss-first-login-checklist/", dismiss_first_login_checklist, name="dismiss_first_login_checklist"),
    path("backend/tour-complete/", mark_tour_complete, name="mark_tour_complete"),
    path("backend/ops-watch/", backend_ops_watch_data, name="backend_ops_watch_data"),
    path("backend-dashboard/", backend_dashboard, name="backend_dashboard_alt"),
    path("backend/import/", backend_entity_import, name="backend_entity_import"),
    path("backend/import-hub/", lambda r: redirect(reverse("studio_os:import_hub"), permanent=False), name="import_hub"),
    path("backend/migration-wizard/", migration_wizard, name="migration_wizard"),
    path("backend/migration-runs/", migration_run_list, name="migration_run_list"),
    path("backend/migration-runs/<int:run_id>/rollback/", migration_rollback, name="migration_rollback"),
    path("backend/migration-runs/<int:run_id>/legacy/", migration_legacy_view, name="migration_legacy_view"),
    path("backend/legacy-data-cleaner/", legacy_data_cleaner_view, name="legacy_data_cleaner"),
    path("backend/entities/", backend_entity_console, name="backend_entity_console"),
    path("workflow/", lambda r: redirect(reverse("studio_os:workflow_center"), permanent=False), name="workflow_center"),
    path("workflow/approvals/", lambda r: redirect(reverse("studio_os:approval_hub"), permanent=False), name="approval_workflow_hub"),
    path("workflow/automation/", automation_hub, name="automation_hub"),
    path("workflow/clone-year/", clone_year_setup, name="clone_year_setup"),
    path("workflow/rollover/", rollover_year, name="rollover_year"),
    path("workflow/rollover/queue/", rollover_queue, name="rollover_queue"),
    path("workflow/rollover/prepare/", rollover_prepare, name="rollover_prepare"),
    path("workflow/rollover/proposal/<int:proposal_id>/", rollover_proposal_detail, name="rollover_proposal_detail"),
    path("workflow/academic-rules/", academic_rules, name="academic_rules"),
    path("certification/", certification_home, name="certification_home"),
    path("certification/session/<int:session_id>/", certification_session_detail, name="certification_session_detail"),
    path("certification/session/<int:session_id>/export.zip", certification_export_zip, name="certification_export_zip"),
    path("certification/session/<int:session_id>/bulk-add/", certification_bulk_add_candidates, name="certification_bulk_add_candidates"),
    path("certification/session/<int:session_id>/override/", certification_session_override, name="certification_session_override"),
    path("claim-invite/", claim_invite, name="claim_invite"),
    path("mfa/setup/", mfa_setup, name="mfa_setup"),
    path("mfa/dismiss-banner/", dismiss_mfa_banner, name="dismiss_mfa_banner"),
    path("mfa/verify/", mfa_verify, name="mfa_verify"),
    path("mfa/passkey/registration/options/", passkey_registration_options, name="passkey_registration_options"),
    path("mfa/passkey/registration/verify/", passkey_registration_verify, name="passkey_registration_verify"),
    path("mfa/passkey/authentication/options/", passkey_authentication_options, name="passkey_authentication_options"),
    path("mfa/passkey/authentication/verify/", passkey_authentication_verify, name="passkey_authentication_verify"),
    path("profile/security/strength/", api_security_strength, name="api_security_strength"),
    path("profile/security/activity/", api_security_activity, name="api_security_activity"),
    path("profile/security/export/", api_security_export_log, name="api_security_export_log"),
    path("profile/security/lockdown/", api_security_lockdown, name="api_security_lockdown"),
    path("profile/security/sessions/", sessions_page, name="sessions_page"),
    path("profile/security/sessions/<str:session_key>/revoke/", sessions_revoke, name="sessions_revoke"),
    path("oidc/start/<str:integration_ref>/", oidc_start, name="oidc_start"),
    path("oidc/callback/<int:integration_id>/", oidc_callback, name="oidc_callback"),
    path("saml/start/<str:integration_ref>/", saml_start, name="saml_start"),
    path("saml/acs/<int:integration_id>/", saml_acs, name="saml_acs"),
    path("saml/metadata/<int:integration_id>/", saml_metadata, name="saml_metadata"),
    
    # Backend UI for People Management
    path("backend/students/", backend_student_list, name="backend_student_list") if BACKEND_PEOPLE_AVAILABLE else None,
    path("backend/alumni/", alumni_list, name="backend_alumni_list") if BACKEND_PEOPLE_AVAILABLE else None,
    path("backend/students/create/", backend_student_create, name="backend_student_create") if BACKEND_PEOPLE_AVAILABLE else None,
    path("backend/teachers/", backend_teacher_list, name="backend_teacher_list") if BACKEND_PEOPLE_AVAILABLE else None,
    path("backend/teachers/create/", backend_teacher_create, name="backend_teacher_create") if BACKEND_PEOPLE_AVAILABLE else None,
    path("backend/guardians/", backend_guardian_list, name="backend_guardian_list") if BACKEND_PEOPLE_AVAILABLE else None,
    path("backend/applicants/", backend_applicant_list, name="backend_applicant_list") if BACKEND_PEOPLE_AVAILABLE else None,
    path("backend/applicants/create/", backend_applicant_create, name="backend_applicant_create") if BACKEND_PEOPLE_AVAILABLE else None,
    path("backend/classrooms/", backend_classroom_list, name="backend_classroom_list") if BACKEND_PEOPLE_AVAILABLE else None,
    path("backend/classrooms/create/", backend_classroom_create, name="backend_classroom_create") if BACKEND_PEOPLE_AVAILABLE else None,
]
# Filter out None values
urlpatterns = [p for p in urlpatterns if p is not None]
