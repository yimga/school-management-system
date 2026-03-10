"""
Runtime blueprints bounded-context surface.

These remain state-compatible re-exports for now so operator/runtime code can
move off legacy `apps.siteconfig.*` module paths before the ownership migration.
"""

from apps.policies.models import BlueprintCompatibilityRule, BlueprintPack, TenantBlueprint
from apps.siteconfig.models_dashboard import (
    DashboardLayout,
    DashboardPack,
    DashboardPackAssignment,
    DashboardTemplate,
    DashboardWidget,
    TenantLayoutAssignment,
)
from apps.siteconfig.models import (
    FormDraft,
    OfficialReportTemplate,
    ReportCardStyle,
    ReportCardStyleQuerySet,
    ReportTemplate,
    ThemeLayout,
    UserPreference,
    get_report_card_style_for_student,
)
from apps.siteconfig.models_workflow import (
    TenantWorkflow,
    WorkflowPack,
    WorkflowPackAssignment,
    WorkflowTemplate,
)

Blueprint = BlueprintPack

__all__ = [
    "Blueprint",
    "BlueprintPack",
    "BlueprintCompatibilityRule",
    "DashboardLayout",
    "DashboardPack",
    "DashboardPackAssignment",
    "DashboardTemplate",
    "DashboardWidget",
    "FormDraft",
    "OfficialReportTemplate",
    "ReportCardStyleQuerySet",
    "ReportCardStyle",
    "ReportTemplate",
    "TenantBlueprint",
    "TenantLayoutAssignment",
    "TenantWorkflow",
    "ThemeLayout",
    "UserPreference",
    "WorkflowPack",
    "WorkflowPackAssignment",
    "WorkflowTemplate",
    "get_report_card_style_for_student",
]
