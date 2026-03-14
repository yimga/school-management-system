"""
Runtime blueprints bounded-context ownership surface.

These are proxy-owner models over the current storage layer so runtime,
dashboard, workflow, and blueprint code can migrate off `apps.siteconfig.*`
without a table move first.
"""

from apps.policies.models import (
    BlueprintCompatibilityRule as LegacyBlueprintCompatibilityRule,
    BlueprintPack as LegacyBlueprintPack,
    TenantBlueprint as LegacyTenantBlueprint,
)
# Import from siteconfig submodules to avoid circular import via siteconfig.models.
from apps.siteconfig.models_tooling import (
    FormDraft as LegacyFormDraft,
    OfficialReportTemplate as LegacyOfficialReportTemplate,
    ReportCardStyle as LegacyReportCardStyle,
    ReportCardStyleQuerySet,
    ReportTemplate as LegacyReportTemplate,
    ThemeLayout,
    UserPreference as LegacyUserPreference,
    get_report_card_style_for_student,
)
from apps.siteconfig.models_dashboard import (
    DashboardLayout as LegacyDashboardLayout,
    DashboardPack as LegacyDashboardPack,
    DashboardPackAssignment as LegacyDashboardPackAssignment,
    DashboardTemplate as LegacyDashboardTemplate,
    DashboardUserPreference as LegacyDashboardUserPreference,
    DashboardWidget as LegacyDashboardWidget,
    SUPER_DASHBOARD_DEFAULT_SECTION_ORDER,
    SuperAdminDashboardPreference as LegacySuperAdminDashboardPreference,
    TenantLayoutAssignment as LegacyTenantLayoutAssignment,
    get_dashboard_widget_metadata,
)
from apps.siteconfig.models_workflow import (
    TenantWorkflow as LegacyTenantWorkflow,
    WorkflowPack as LegacyWorkflowPack,
    WorkflowPackAssignment as LegacyWorkflowPackAssignment,
    WorkflowTemplate as LegacyWorkflowTemplate,
)


def _proxy_model(legacy_model, *, app_label: str, doc: str):
    meta = type(
        "Meta",
        (),
        {
            "proxy": True,
            "app_label": app_label,
            "verbose_name": legacy_model._meta.verbose_name,
            "verbose_name_plural": legacy_model._meta.verbose_name_plural,
        },
    )
    return type(
        legacy_model.__name__,
        (legacy_model,),
        {
            "__module__": __name__,
            "__doc__": doc,
            "Meta": meta,
        },
    )


BlueprintPack = _proxy_model(
    LegacyBlueprintPack,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for blueprint catalog entries.",
)
BlueprintCompatibilityRule = _proxy_model(
    LegacyBlueprintCompatibilityRule,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for compatibility rules.",
)
TenantBlueprint = _proxy_model(
    LegacyTenantBlueprint,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for tenant blueprint activation.",
)
DashboardLayout = _proxy_model(
    LegacyDashboardLayout,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for dashboard layout definitions.",
)
DashboardPack = _proxy_model(
    LegacyDashboardPack,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for dashboard packs.",
)
DashboardPackAssignment = _proxy_model(
    LegacyDashboardPackAssignment,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for dashboard pack assignment.",
)
DashboardTemplate = _proxy_model(
    LegacyDashboardTemplate,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for dashboard templates.",
)
DashboardUserPreference = _proxy_model(
    LegacyDashboardUserPreference,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for dashboard user preferences.",
)
DashboardWidget = _proxy_model(
    LegacyDashboardWidget,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for dashboard widget catalog entries.",
)
FormDraft = _proxy_model(
    LegacyFormDraft,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for packageable setup/report form drafts.",
)
OfficialReportTemplate = _proxy_model(
    LegacyOfficialReportTemplate,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for official report templates.",
)
ReportCardStyle = _proxy_model(
    LegacyReportCardStyle,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for report card styling assets.",
)
ReportTemplate = _proxy_model(
    LegacyReportTemplate,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for reusable report templates.",
)
SuperAdminDashboardPreference = _proxy_model(
    LegacySuperAdminDashboardPreference,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for control-plane dashboard layout state.",
)
TenantLayoutAssignment = _proxy_model(
    LegacyTenantLayoutAssignment,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for tenant dashboard layout assignment.",
)
TenantWorkflow = _proxy_model(
    LegacyTenantWorkflow,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for tenant workflow activation.",
)
UserPreference = _proxy_model(
    LegacyUserPreference,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for runtime-facing user preference state.",
)
WorkflowPack = _proxy_model(
    LegacyWorkflowPack,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for workflow packs.",
)
WorkflowPackAssignment = _proxy_model(
    LegacyWorkflowPackAssignment,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for workflow pack assignment.",
)
WorkflowTemplate = _proxy_model(
    LegacyWorkflowTemplate,
    app_label="runtime_blueprints",
    doc="Runtime Blueprints owner surface for workflow templates.",
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
    "DashboardUserPreference",
    "DashboardWidget",
    "FormDraft",
    "OfficialReportTemplate",
    "ReportCardStyleQuerySet",
    "ReportCardStyle",
    "ReportTemplate",
    "SUPER_DASHBOARD_DEFAULT_SECTION_ORDER",
    "SuperAdminDashboardPreference",
    "TenantBlueprint",
    "TenantLayoutAssignment",
    "TenantWorkflow",
    "ThemeLayout",
    "UserPreference",
    "WorkflowPack",
    "WorkflowPackAssignment",
    "WorkflowTemplate",
    "get_dashboard_widget_metadata",
    "get_report_card_style_for_student",
]
