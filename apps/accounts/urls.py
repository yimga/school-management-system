from django.shortcuts import redirect
from django.urls import path, reverse, reverse_lazy
from django.contrib.auth.views import (
    PasswordChangeDoneView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)

from .password_reset import PortalPasswordResetForm

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
    mark_all_notifications_read,
    notification_preferences,
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
from .views_legacy_setup import LegacySetupView
from apps.schools.super_views_operator_team import operator_invite_accept
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
    notification_corner_dismiss,
    notification_corner_mark_read,
    notification_corner_snooze,
    security_posture_review,
    security_posture_session_modal_ack,
    sessions_page,
    sessions_revoke,
)
from .views_oidc import oidc_start, oidc_callback, oidc_logout
from .views_saml import saml_start, saml_acs, saml_metadata
from .views_impersonation import impersonate_entry, end_impersonation
from .views_district_interop import (
    district_interop_csv_classes,
    district_interop_csv_students,
    district_interop_csv_teachers,
    district_interop_native_probe,
    district_interop_packet,
    district_interop_partner,
    district_interop_rotate_token,
    district_interop_save_advanced,
    district_interop_save_native_vendor,
    district_interop_toggle_synthetic,
    district_lms_interop,
    institution_profile_wizard,
)
from apps.schools.views_advancement import (
    advancement_donor_create,
    advancement_donor_detail,
    advancement_donor_edit,
    advancement_donor_list,
    advancement_gift_delete,
)
from apps.accounts.views_tenant_observability import tenant_activity_log
from apps.accounts.views_trust_hub import security_trust_hub, tenant_impersonation_audit
from apps.accounts.views_tenant_identity import (
    tenant_identity_detail,
    tenant_identity_invite,
    tenant_identity_offboard,
    tenant_identity_regulator_grant,
    tenant_identity_revoke_sessions,
    tenant_identity_roster,
    tenant_staff_invite_accept,
)
from apps.schoolops.views_tenant_ops import (
    ops_canteen,
    ops_clinic,
    ops_hub,
    ops_inventory,
    ops_library,
    ops_substitutes,
    ops_timetabling,
    ops_transport,
    ops_visitor_log,
    ops_facilities,
    ops_pos,
)
from apps.schoolops.views_substitute_handover import substitute_handover_create
from apps.schoolops.views_lost_belongings import (
    lost_belongings_mint,
    lost_belongings_lookup,
    lost_belongings_recover,
)
from apps.finance.views_permission_to_pay import (
    permission_to_pay_open,
    permission_to_pay_approve,
    permission_to_pay_authorize,
)

try:
    from apps.people.views_backend import (
        backend_student_list,
        backend_student_create,
        backend_student_detail,
        backend_teacher_list,
        backend_teacher_create,
        backend_teacher_detail,
        backend_classroom_list,
        backend_classroom_create,
        backend_classroom_detail,
        backend_guardian_list,
        backend_applicant_list,
        backend_applicant_create,
        alumni_list,
    )
    from apps.people.views_backend_bulk import backend_student_bulk_status

    BACKEND_PEOPLE_AVAILABLE = True
except ImportError:
    BACKEND_PEOPLE_AVAILABLE = False
    backend_student_list = backend_student_create = alumni_list = None
    backend_teacher_list = backend_teacher_create = backend_teacher_detail = (
        backend_classroom_list
    ) = backend_classroom_create = backend_classroom_detail = backend_guardian_list = (
        backend_applicant_list
    ) = None

app_name = "accounts"

urlpatterns = [
    path("", auth_root_redirect, name="root"),  # rbac-allow: pre-auth dispatcher
    path("login/", login_view, name="login"),  # rbac-allow: login page must be anonymous-reachable
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
    path(
        "profile/delegations/<int:pk>/revoke/",
        delegation_revoke,
        name="delegation_revoke",
    ),
    path(
        "profile/delegations/catch-up/", delegation_catch_up, name="delegation_catch_up"
    ),
    path(
        "profile/password/",
        PasswordChangeView.as_view(
            template_name="accounts/password_change_form.html",
            success_url=reverse_lazy("accounts:password_change_done"),
        ),
        name="password_change",
    ),
    path(
        "profile/password/done/",
        PasswordChangeDoneView.as_view(
            template_name="accounts/password_change_done.html",
        ),
        name="password_change_done",
    ),
    path("notifications/", user_notifications, name="user_notifications"),
    path(
        "notifications/mark-all-read/",
        mark_all_notifications_read,
        name="mark_all_notifications_read",
    ),
    path(
        "notifications/preferences/",
        notification_preferences,
        name="notification_preferences",
    ),
    path("messages/", user_messages, name="user_messages"),
    path("messages/direct/compose/", direct_compose, name="direct_compose"),
    path("messages/direct/<int:user_id>/", direct_thread, name="direct_thread"),
    path("documentation/", user_documentation, name="user_documentation"),
    path("rbac/", rbac_dashboard, name="rbac"),
    path("backend/", backend_dashboard, name="backend_dashboard"),
    path("backend/request-waiver/", request_waiver, name="request_waiver"),
    path(
        "backend/district-lms-interop/",
        district_lms_interop,
        name="district_lms_interop",
    ),
    path(
        "backend/district-lms-interop/rotate-token/",
        district_interop_rotate_token,
        name="district_interop_rotate_token",
    ),
    path(
        "backend/district-lms-interop/export/students.csv",
        district_interop_csv_students,
        name="district_interop_csv_students",
    ),
    path(
        "backend/district-lms-interop/export/teachers.csv",
        district_interop_csv_teachers,
        name="district_interop_csv_teachers",
    ),
    path(
        "backend/district-lms-interop/export/classes.csv",
        district_interop_csv_classes,
        name="district_interop_csv_classes",
    ),
    path(
        "backend/advancement/donors/",
        advancement_donor_list,
        name="advancement_donor_list",
    ),
    path(
        "backend/advancement/donors/add/",
        advancement_donor_create,
        name="advancement_donor_create",
    ),
    path(
        "backend/advancement/donors/<int:donor_id>/",
        advancement_donor_detail,
        name="advancement_donor_detail",
    ),
    path(
        "backend/advancement/donors/<int:donor_id>/edit/",
        advancement_donor_edit,
        name="advancement_donor_edit",
    ),
    path(
        "backend/advancement/gifts/<int:gift_id>/delete/",
        advancement_gift_delete,
        name="advancement_gift_delete",
    ),
    path("backend/activity-log/", tenant_activity_log, name="tenant_activity_log"),
    path(
        "backend/security-trust/",
        security_trust_hub,
        name="security_trust_hub",
    ),
    path(
        "backend/security-trust/impersonation/",
        tenant_impersonation_audit,
        name="tenant_impersonation_audit",
    ),
    path(
        "backend/identity/",
        tenant_identity_roster,
        name="tenant_identity_roster",
    ),
    path(
        "backend/identity/invite/",
        tenant_identity_invite,
        name="tenant_identity_invite",
    ),
    path(
        "backend/identity/regulator-grant/",
        tenant_identity_regulator_grant,
        name="tenant_identity_regulator_grant",
    ),
    path(
        "backend/identity/<int:user_id>/",
        tenant_identity_detail,
        name="tenant_identity_detail",
    ),
    path(
        "backend/identity/<int:user_id>/offboard/",
        tenant_identity_offboard,
        name="tenant_identity_offboard",
    ),
    path(
        "backend/identity/<int:user_id>/revoke-sessions/",
        tenant_identity_revoke_sessions,
        name="tenant_identity_revoke_sessions",
    ),
    path("backend/ops/", ops_hub, name="ops_hub"),
    path("backend/ops/library/", ops_library, name="ops_library"),
    path("backend/ops/transport/", ops_transport, name="ops_transport"),
    path("backend/ops/inventory/", ops_inventory, name="ops_inventory"),
    path("backend/ops/canteen/", ops_canteen, name="ops_canteen"),
    path("backend/ops/clinic/", ops_clinic, name="ops_clinic"),
    path("backend/ops/timetabling/", ops_timetabling, name="ops_timetabling"),
    path(
        "backend/ops/substitutes/",
        ops_substitutes,
        name="ops_substitutes",
    ),
    path(
        "backend/ops/substitutes/handover/",
        substitute_handover_create,
        name="substitute_handover_create",
    ),
    path(
        "backend/finance/permission-to-pay/",
        permission_to_pay_open,
        name="permission_to_pay_open",
    ),
    path(
        "backend/finance/permission-to-pay/approve/",
        permission_to_pay_approve,
        name="permission_to_pay_approve",
    ),
    path(
        "backend/finance/permission-to-pay/authorize/",
        permission_to_pay_authorize,
        name="permission_to_pay_authorize",
    ),
    path(
        "backend/ops/lost-belongings/mint/",
        lost_belongings_mint,
        name="lost_belongings_mint",
    ),
    path(
        "backend/ops/lost-belongings/recover/",
        lost_belongings_recover,
        name="lost_belongings_recover",
    ),
    path(
        "lost-found/",
        lost_belongings_lookup,
        name="lost_belongings_lookup",
    ),
    path(
        "backend/ops/visitors/",
        ops_visitor_log,
        name="ops_visitor_log",
    ),
    path(
        "backend/ops/facilities/",
        ops_facilities,
        name="ops_facilities",
    ),
    path("backend/ops/pos/", ops_pos, name="ops_pos"),
    path(
        "backend/district-lms-interop/advanced/",
        district_interop_save_advanced,
        name="district_interop_save_advanced",
    ),
    path(
        "backend/district-lms-interop/native-vendor/",
        district_interop_save_native_vendor,
        name="district_interop_save_native_vendor",
    ),
    path(
        "backend/district-lms-interop/native-probe/",
        district_interop_native_probe,
        name="district_interop_native_probe",
    ),
    path(
        "backend/district-lms-interop/synthetic/",
        district_interop_toggle_synthetic,
        name="district_interop_toggle_synthetic",
    ),
    path(
        "backend/district-lms-interop/packet/",
        district_interop_packet,
        name="district_interop_packet",
    ),
    path(
        "backend/district-lms-interop/partner/",
        district_interop_partner,
        name="district_interop_partner",
    ),
    path(
        "backend/institution-profile/",
        institution_profile_wizard,
        name="institution_profile_wizard",
    ),
    path(
        "backend/status/fragment/",
        backend_dashboard_status_fragment,
        name="backend_dashboard_status_fragment",
    ),
    path(
        "backend/dismiss-first-login-checklist/",
        dismiss_first_login_checklist,
        name="dismiss_first_login_checklist",
    ),
    path("backend/tour-complete/", mark_tour_complete, name="mark_tour_complete"),
    path("backend/ops-watch/", backend_ops_watch_data, name="backend_ops_watch_data"),
    path("backend-dashboard/", backend_dashboard, name="backend_dashboard_alt"),
    path("backend/import/", backend_entity_import, name="backend_entity_import"),
    path(
        "backend/import-hub/",
        lambda r: redirect(reverse("studio_os:import_hub"), permanent=False),
        name="import_hub",
    ),
    path("backend/migration-wizard/", migration_wizard, name="migration_wizard"),
    path("backend/migration-runs/", migration_run_list, name="migration_run_list"),
    path(
        "backend/migration-runs/<int:run_id>/rollback/",
        migration_rollback,
        name="migration_rollback",
    ),
    path(
        "backend/migration-runs/<int:run_id>/legacy/",
        migration_legacy_view,
        name="migration_legacy_view",
    ),
    path(
        "backend/legacy-data-cleaner/",
        legacy_data_cleaner_view,
        name="legacy_data_cleaner",
    ),
    path("backend/entities/", backend_entity_console, name="backend_entity_console"),
    path(
        "workflow/",
        lambda r: redirect(reverse("studio_os:workflow_center"), permanent=False),
        name="workflow_center",
    ),
    path(
        "workflow/approvals/",
        lambda r: redirect(reverse("studio_os:approval_hub"), permanent=False),
        name="approval_workflow_hub",
    ),
    path("workflow/automation/", automation_hub, name="automation_hub"),
    path("workflow/clone-year/", clone_year_setup, name="clone_year_setup"),
    path("workflow/rollover/", rollover_year, name="rollover_year"),
    path("workflow/rollover/queue/", rollover_queue, name="rollover_queue"),
    path("workflow/rollover/prepare/", rollover_prepare, name="rollover_prepare"),
    path(
        "workflow/rollover/proposal/<int:proposal_id>/",
        rollover_proposal_detail,
        name="rollover_proposal_detail",
    ),
    path("workflow/academic-rules/", academic_rules, name="academic_rules"),
    path("certification/", certification_home, name="certification_home"),
    path(
        "certification/session/<int:session_id>/",
        certification_session_detail,
        name="certification_session_detail",
    ),
    path(
        "certification/session/<int:session_id>/export.zip",
        certification_export_zip,
        name="certification_export_zip",
    ),
    path(
        "certification/session/<int:session_id>/bulk-add/",
        certification_bulk_add_candidates,
        name="certification_bulk_add_candidates",
    ),
    path(
        "certification/session/<int:session_id>/override/",
        certification_session_override,
        name="certification_session_override",
    ),
    path(
        "password_reset/",
        PasswordResetView.as_view(
            form_class=PortalPasswordResetForm,
            template_name="registration/password_reset_form.html",
            email_template_name="emails/password_reset.txt",
            html_email_template_name="emails/password_reset.html",
            subject_template_name="registration/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),  # rbac-allow: anonymous password recovery
    path(
        "password_reset/done/",
        PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
    path("claim-invite/", claim_invite, name="claim_invite"),
    path(
        "operator-invite/<uuid:token>/",
        operator_invite_accept,
        name="operator_invite_accept",
    ),  # rbac-allow: anonymous operator invite acceptance
    path(
        "staff-invite/<uuid:token>/",
        tenant_staff_invite_accept,
        name="tenant_staff_invite_accept",
    ),  # rbac-allow: anonymous tenant staff invite acceptance
    # v3.29 migration-cloud sunset job: one-time setup link landing page for
    # users emailed by accounts.sunset_stale_legacy_hashes. Token-validated
    # by Django's PasswordResetConfirmView parent; view additionally clears
    # the three legacy_* fields atomically on form_valid.
    # rbac-allow: token-authenticated legacy-hash one-time setup; must be anonymous-reachable
    path(
        "legacy-setup/<uidb64>/<token>/",
        LegacySetupView.as_view(),
        name="legacy_setup",
    ),
    path("mfa/setup/", mfa_setup, name="mfa_setup"),
    path("mfa/dismiss-banner/", dismiss_mfa_banner, name="dismiss_mfa_banner"),
    path("mfa/verify/", mfa_verify, name="mfa_verify"),
    path(
        "mfa/passkey/registration/options/",
        passkey_registration_options,
        name="passkey_registration_options",
    ),
    path(
        "mfa/passkey/registration/verify/",
        passkey_registration_verify,
        name="passkey_registration_verify",
    ),
    path(
        "mfa/passkey/authentication/options/",
        passkey_authentication_options,
        name="passkey_authentication_options",
    ),
    path(
        "mfa/passkey/authentication/verify/",
        passkey_authentication_verify,
        name="passkey_authentication_verify",
    ),
    path(
        "profile/security/strength/",
        api_security_strength,
        name="api_security_strength",
    ),
    path(
        "profile/security/review/",
        security_posture_review,
        name="security_posture_review",
    ),
    path(
        "profile/security/session-modal/ack/",
        security_posture_session_modal_ack,
        name="security_posture_session_modal_ack",
    ),
    path(
        "notifications/corner/snooze/",
        notification_corner_snooze,
        name="notification_corner_snooze",
    ),
    path(
        "notifications/corner/dismiss/",
        notification_corner_dismiss,
        name="notification_corner_dismiss",
    ),
    path(
        "notifications/corner/mark-read/",
        notification_corner_mark_read,
        name="notification_corner_mark_read",
    ),
    path(
        "profile/security/activity/",
        api_security_activity,
        name="api_security_activity",
    ),
    path(
        "profile/security/export/",
        api_security_export_log,
        name="api_security_export_log",
    ),
    path(
        "profile/security/lockdown/",
        api_security_lockdown,
        name="api_security_lockdown",
    ),
    path("profile/security/sessions/", sessions_page, name="sessions_page"),
    path(
        "profile/security/sessions/<str:session_key>/revoke/",
        sessions_revoke,
        name="sessions_revoke",
    ),
    path("oidc/start/<str:integration_ref>/", oidc_start, name="oidc_start"),  # rbac-allow: pre-auth OIDC kickoff (user not logged in yet)
    path("oidc/callback/<int:integration_id>/", oidc_callback, name="oidc_callback"),  # rbac-allow: pre-auth OIDC callback (state-token auth)
    path("oidc/logout/<int:integration_id>/", oidc_logout, name="oidc_logout"),  # rbac-allow: post-logout OIDC redirect
    path("saml/start/<str:integration_ref>/", saml_start, name="saml_start"),  # rbac-allow: pre-auth SAML kickoff (user not logged in yet)
    path("saml/acs/<int:integration_id>/", saml_acs, name="saml_acs"),  # rbac-allow: pre-auth SAML assertion-consumer (signature-verified by view)
    path("saml/metadata/<int:integration_id>/", saml_metadata, name="saml_metadata"),  # rbac-allow: SAML metadata XML must be publicly fetchable
    # Backend UI for People Management
    path("backend/students/", backend_student_list, name="backend_student_list")
    if BACKEND_PEOPLE_AVAILABLE
    else None,
    path(
        "backend/students/bulk/status/",
        backend_student_bulk_status,
        name="backend_student_bulk_status",
    )
    if BACKEND_PEOPLE_AVAILABLE
    else None,
    path("backend/alumni/", alumni_list, name="backend_alumni_list")
    if BACKEND_PEOPLE_AVAILABLE
    else None,
    path(
        "backend/students/create/",
        backend_student_create,
        name="backend_student_create",
    )
    if BACKEND_PEOPLE_AVAILABLE
    else None,
    path(
        "backend/students/<int:student_id>/",
        backend_student_detail,
        name="backend_student_detail",
    )
    if BACKEND_PEOPLE_AVAILABLE
    else None,
    path("backend/teachers/", backend_teacher_list, name="backend_teacher_list")
    if BACKEND_PEOPLE_AVAILABLE
    else None,
    path(
        "backend/teachers/create/",
        backend_teacher_create,
        name="backend_teacher_create",
    )
    if BACKEND_PEOPLE_AVAILABLE
    else None,
    path(
        "backend/teachers/<int:teacher_id>/",
        backend_teacher_detail,
        name="backend_teacher_detail",
    )
    if BACKEND_PEOPLE_AVAILABLE
    else None,
    path("backend/guardians/", backend_guardian_list, name="backend_guardian_list")
    if BACKEND_PEOPLE_AVAILABLE
    else None,
    path("backend/applicants/", backend_applicant_list, name="backend_applicant_list")
    if BACKEND_PEOPLE_AVAILABLE
    else None,
    path(
        "backend/applicants/create/",
        backend_applicant_create,
        name="backend_applicant_create",
    )
    if BACKEND_PEOPLE_AVAILABLE
    else None,
    path("backend/classrooms/", backend_classroom_list, name="backend_classroom_list")
    if BACKEND_PEOPLE_AVAILABLE
    else None,
    path(
        "backend/classrooms/create/",
        backend_classroom_create,
        name="backend_classroom_create",
    )
    if BACKEND_PEOPLE_AVAILABLE
    else None,
    path(
        "backend/classrooms/<int:classroom_id>/",
        backend_classroom_detail,
        name="backend_classroom_detail",
    )
    if BACKEND_PEOPLE_AVAILABLE
    else None,
]
# Filter out None values
urlpatterns = [p for p in urlpatterns if p is not None]
