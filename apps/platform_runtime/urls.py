from django.urls import path

from apps.platform_runtime.views_operational_center import (
    implementation_command_center,
    implementation_missing_data_blockers_json,
    pilot_defect_dashboard,
    pilot_evidence_dashboard,
    support_playbook_center,
)
from apps.platform_runtime.views_tenant_lifecycle import tenant_lifecycle_dashboard

urlpatterns = [
    path(
        "lifecycle/",
        tenant_lifecycle_dashboard,
        name="tenant_lifecycle_dashboard",
    ),
    path(
        "implementation/",
        implementation_command_center,
        name="implementation_command_center",
    ),
    path(
        "implementation/blockers.json",
        implementation_missing_data_blockers_json,
        name="implementation_missing_data_blockers_json",
    ),
    path(
        "support-playbooks/",
        support_playbook_center,
        name="support_playbook_center",
    ),
    path(
        "pilot-evidence/",
        pilot_evidence_dashboard,
        name="pilot_evidence_dashboard",
    ),
    path(
        "pilot-defects/",
        pilot_defect_dashboard,
        name="pilot_defect_dashboard",
    ),
]
