"""
Modular configuration facade for site and tenant runtime settings.

This module is the application-facing entry point for configuration reads. It
keeps legacy runtime compatibility behind one service boundary while exposing
domain-specific config objects to views, services, and templates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class GuidedConfigurationWorkflow:
    current_state: str
    missing_setup: tuple[str, ...] = ()
    recommended_next_step: str = ""
    safe_fix_label: str = "Open guided setup"
    safe_fix_url_name: str = ""


@dataclass(frozen=True)
class BaseDomainConfig:
    key: str
    label: str
    values: dict[str, Any] = field(default_factory=dict)
    workflow: GuidedConfigurationWorkflow = field(
        default_factory=GuidedConfigurationWorkflow
    )


@dataclass(frozen=True)
class BrandConfig(BaseDomainConfig):
    key: str = "brand"
    label: str = "Brand"


@dataclass(frozen=True)
class FinanceConfig(BaseDomainConfig):
    key: str = "finance"
    label: str = "Finance"


@dataclass(frozen=True)
class PaymentConfig(BaseDomainConfig):
    key: str = "payment"
    label: str = "Payment"


@dataclass(frozen=True)
class ReportConfig(BaseDomainConfig):
    key: str = "report"
    label: str = "Reports"


@dataclass(frozen=True)
class CommunicationConfig(BaseDomainConfig):
    key: str = "communication"
    label: str = "Communication"


@dataclass(frozen=True)
class SecurityConfig(BaseDomainConfig):
    key: str = "security"
    label: str = "Security"


@dataclass(frozen=True)
class RegionalConfig(BaseDomainConfig):
    key: str = "regional"
    label: str = "Regional"


@dataclass(frozen=True)
class MarketplaceConfig(BaseDomainConfig):
    key: str = "marketplace"
    label: str = "Marketplace"


@dataclass(frozen=True)
class TenantRuntimeConfig(BaseDomainConfig):
    key: str = "tenant_runtime"
    label: str = "Tenant runtime"


@dataclass(frozen=True)
class ModularConfigurationBundle:
    brand: BrandConfig
    finance: FinanceConfig
    payment: PaymentConfig
    report: ReportConfig
    communication: CommunicationConfig
    security: SecurityConfig
    regional: RegionalConfig
    marketplace: MarketplaceConfig
    tenant_runtime: TenantRuntimeConfig

    @property
    def configs(self) -> tuple[BaseDomainConfig, ...]:
        return (
            self.brand,
            self.finance,
            self.payment,
            self.report,
            self.communication,
            self.security,
            self.regional,
            self.marketplace,
            self.tenant_runtime,
        )


def get_effective_site_settings(request: Any = None, school: Any = None) -> Any:
    try:
        from apps.platform_runtime.helpers import (
            get_effective_site_settings as resolver,
        )

        return resolver(request=request, school=school)
    except Exception:
        return None


def get_platform_site_settings_record(*, create: bool = False) -> Any:
    from apps.platform_runtime.helpers import (
        get_platform_site_settings_record as resolver,
    )

    return resolver(create=create)


def invalidate_effective_site_settings_cache() -> None:
    from apps.platform_runtime.helpers import (
        invalidate_effective_site_settings_cache as invalidate,
    )

    invalidate()


def persist_platform_runtime_payload_updates(updates: dict[str, object]) -> None:
    from apps.platform_runtime.helpers import (
        persist_platform_runtime_payload_updates as persist,
    )

    persist(updates)


def get_effective_flags(request: Any = None) -> dict:
    try:
        from apps.platform_runtime.helpers import get_effective_flags as resolver

        return resolver(request)
    except Exception:
        return {}


def get_effective_feature_control_settings(
    request: Any = None, school: Any = None
) -> dict[str, Any]:
    try:
        from apps.platform_runtime.helpers import (
            get_effective_feature_control_settings as resolver,
        )

        return resolver(request=request, school=school)
    except Exception:
        return {}


def get_effective_offline_runtime_settings(
    request: Any = None, school: Any = None
) -> dict[str, Any]:
    try:
        from apps.platform_runtime.helpers import (
            get_effective_offline_runtime_settings as resolver,
        )

        return resolver(request=request, school=school)
    except Exception:
        return {
            "enable_offline_mode": False,
            "offline_sync_conflict_resolution": "show_both",
            "backend_feature_flags": {},
        }


def get_effective_support_contact_settings(
    request: Any = None, school: Any = None
) -> dict[str, str]:
    try:
        from apps.platform_runtime.helpers import (
            get_effective_support_contact_settings as resolver,
        )

        return resolver(request=request, school=school)
    except Exception:
        return {}


def get_effective_marketplace_integration_settings(
    request: Any = None, school: Any = None
) -> dict[str, object]:
    try:
        from apps.platform_runtime.helpers import (
            get_effective_marketplace_integration_settings as resolver,
        )

        return resolver(request=request, school=school)
    except Exception:
        return {
            "marksheet_ocr_command": "",
            "marksheet_ocr_api_key": "",
            "sms_provider": "console",
            "sms_api_key": "",
            "ai_provider_api_key": "",
            "whatsapp_api_token": "",
            "sms_sender_id": "RUNMYCAMPUS",
            "email_from_address": "noreply@school.example.com",
            "smtp_password": "",
            "webhook_signing_secret": "",
            "marketplace_partner_client_secret": "",
            "whatsapp_support_number": "",
            "whatsapp_admissions_number": "",
        }


def get_legacy_site_settings_compat(request: Any = None, school: Any = None) -> Any:
    """
    Compatibility bridge for code that still needs the effective legacy shape.

    New code should consume the domain config objects below. This bridge keeps
    the ORM singleton hidden behind the runtime resolver.
    """
    return get_effective_site_settings(request=request, school=school)


def _call_dict(obj: Any, method_name: str) -> dict[str, Any]:
    method = getattr(obj, method_name, None)
    if not callable(method):
        return {}
    try:
        value = method()
    except (AttributeError, LookupError, RuntimeError, TypeError, ValueError):
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _state(is_ready: bool, ready: str, missing: str) -> str:
    return ready if is_ready else missing


def _workflow(
    *,
    is_ready: bool,
    ready: str,
    missing: list[str],
    next_step: str,
    url_name: str,
    label: str = "Open guided setup",
) -> GuidedConfigurationWorkflow:
    return GuidedConfigurationWorkflow(
        current_state=_state(is_ready, ready, "Missing setup"),
        missing_setup=tuple(missing),
        recommended_next_step="No action required" if is_ready else next_step,
        safe_fix_label=label,
        safe_fix_url_name=url_name,
    )


def get_brand_config(request: Any = None, school: Any = None) -> BrandConfig:
    site = get_legacy_site_settings_compat(request=request, school=school)
    metadata = _call_dict(site, "get_brand_metadata")
    theme = _call_dict(site, "get_theme_experience_settings")
    values = {**metadata, **theme}
    missing: list[str] = []
    if not values.get("school_name") and not values.get("site_name"):
        missing.append("School or platform display name")
    if not values.get("primary_color"):
        missing.append("Primary brand color")
    if not values.get("theme_pack_id"):
        missing.append("Theme pack")
    return BrandConfig(
        values=values,
        workflow=_workflow(
            is_ready=not missing,
            ready="Brand ready",
            missing=missing,
            next_step="Complete the theme and brand guided setup.",
            url_name="siteconfig:theme_colors",
            label="Fix brand setup",
        ),
    )


def get_finance_config(request: Any = None, school: Any = None) -> FinanceConfig:
    site = get_legacy_site_settings_compat(request=request, school=school)
    values = _call_dict(site, "get_finance_runtime_config")
    enabled = bool(values.get("auto_generate_invoices_enabled"))
    missing = [] if enabled else ["Invoice automation policy"]
    return FinanceConfig(
        values=values,
        workflow=_workflow(
            is_ready=not missing,
            ready="Finance automation configured",
            missing=missing,
            next_step="Review finance automation and approval policy.",
            url_name="siteconfig:billing_plan_readonly",
            label="Open finance setup",
        ),
    )


def get_payment_config(request: Any = None, school: Any = None) -> PaymentConfig:
    site = get_legacy_site_settings_compat(request=request, school=school)
    finance = _call_dict(site, "get_finance_runtime_config")
    marketplace = get_effective_marketplace_integration_settings(
        request=request, school=school
    )
    values = {
        "receipt_upload_enabled": finance.get("receipt_upload_enabled"),
        "receipt_auto_verify_enabled": finance.get("receipt_auto_verify_enabled"),
        "receipt_verification_method": finance.get("receipt_verification_method"),
        "bank_verification_enabled": finance.get("bank_verification_enabled"),
        "email_from_address": marketplace.get("email_from_address"),
    }
    missing = []
    if not values.get("receipt_upload_enabled"):
        missing.append("Receipt upload")
    if not values.get("email_from_address"):
        missing.append("Payment email sender")
    return PaymentConfig(
        values=values,
        workflow=_workflow(
            is_ready=not missing,
            ready="Payment intake configured",
            missing=missing,
            next_step="Enable receipt intake and confirm payment sender identity.",
            url_name="siteconfig:billing_plan_readonly",
            label="Fix payment setup",
        ),
    )


def get_report_config(request: Any = None, school: Any = None) -> ReportConfig:
    site = get_legacy_site_settings_compat(request=request, school=school)
    preview = _call_dict(site, "get_report_preview_settings")
    feature = get_effective_feature_control_settings(request=request, school=school)
    values = {
        **preview,
        "report_downloads_enabled": feature.get("report_downloads_enabled"),
        "reports_require_approved_grades_before_publish": feature.get(
            "reports_require_approved_grades_before_publish"
        ),
        "reports_use_approved_grades_only": feature.get(
            "reports_use_approved_grades_only"
        ),
    }
    missing = []
    if not values.get("default_report_type"):
        missing.append("Default report type")
    if not values.get("contact_email"):
        missing.append("Report contact email")
    return ReportConfig(
        values=values,
        workflow=_workflow(
            is_ready=not missing,
            ready="Report defaults configured",
            missing=missing,
            next_step="Choose report defaults and contact details.",
            url_name="siteconfig:scheduled_reports_delivery_hub",
            label="Fix report setup",
        ),
    )


def get_communication_config(
    request: Any = None, school: Any = None
) -> CommunicationConfig:
    feature = get_effective_feature_control_settings(request=request, school=school)
    support = get_effective_support_contact_settings(request=request, school=school)
    marketplace = get_effective_marketplace_integration_settings(
        request=request, school=school
    )
    values = {
        "notification_channels": list(feature.get("notification_channels") or []),
        **support,
        "sms_provider": marketplace.get("sms_provider"),
        "sms_sender_id": marketplace.get("sms_sender_id"),
        "email_from_address": marketplace.get("email_from_address"),
    }
    missing = []
    if not values["notification_channels"]:
        missing.append("Notification channels")
    if values.get("sms_provider") not in (None, "", "console") and not marketplace.get(
        "sms_api_key"
    ):
        missing.append("SMS provider credential")
    return CommunicationConfig(
        values=values,
        workflow=_workflow(
            is_ready=not missing,
            ready="Communication channels configured",
            missing=missing,
            next_step="Set delivery channels and sender defaults.",
            url_name="siteconfig:feature_control_panel",
            label="Fix communication setup",
        ),
    )


def get_security_config(request: Any = None, school: Any = None) -> SecurityConfig:
    feature = get_effective_feature_control_settings(request=request, school=school)
    values = {
        "require_mfa_all_staff": bool(feature.get("require_mfa_all_staff", False)),
        "require_mfa_roles": list(feature.get("require_mfa_roles") or []),
        "maintenance_mode": bool(feature.get("maintenance_mode", False)),
        "backend_feature_flags": dict(feature.get("backend_feature_flags") or {}),
    }
    missing = []
    if not values["require_mfa_all_staff"] and not values["require_mfa_roles"]:
        missing.append("MFA requirement")
    return SecurityConfig(
        values=values,
        workflow=_workflow(
            is_ready=not missing,
            ready="Security policy configured",
            missing=missing,
            next_step="Enable MFA for staff or role-based access.",
            url_name="siteconfig:feature_control_panel",
            label="Fix security setup",
        ),
    )


def get_regional_config(request: Any = None, school: Any = None) -> RegionalConfig:
    if school is None and request is not None:
        school = getattr(request, "school", None)
    site = get_legacy_site_settings_compat(request=request, school=school)
    region = getattr(school, "default_region", None) if school is not None else None
    values = {
        "school_region": getattr(region, "name", None),
        "timezone": getattr(region, "timezone", None),
        "currency": getattr(region, "default_currency", None),
        "country": getattr(site, "country", None) if site is not None else None,
        "region": getattr(site, "region", None) if site is not None else None,
        "ministry": getattr(site, "ministry", None) if site is not None else None,
    }
    missing = []
    if not values["school_region"]:
        missing.append("School region profile")
    if not values["timezone"]:
        missing.append("Timezone")
    if not values["currency"]:
        missing.append("Currency")
    return RegionalConfig(
        values=values,
        workflow=_workflow(
            is_ready=not missing,
            ready="Regional defaults configured",
            missing=missing,
            next_step="Attach a region profile with timezone and currency.",
            url_name="siteconfig:region_validation",
            label="Fix regional setup",
        ),
    )


def get_marketplace_config(
    request: Any = None, school: Any = None
) -> MarketplaceConfig:
    values = get_effective_marketplace_integration_settings(
        request=request, school=school
    )
    missing = []
    if not values.get("webhook_signing_secret"):
        missing.append("Webhook signing secret")
    if not values.get("email_from_address"):
        missing.append("Marketplace email sender")
    return MarketplaceConfig(
        values=values,
        workflow=_workflow(
            is_ready=not missing,
            ready="Marketplace integration configured",
            missing=missing,
            next_step="Set integration sender and webhook credentials.",
            url_name="siteconfig:feature_control_panel",
            label="Fix marketplace setup",
        ),
    )


def get_tenant_runtime_config(
    request: Any = None, school: Any = None
) -> TenantRuntimeConfig:
    if school is None and request is not None:
        school = getattr(request, "school", None)
    site = get_legacy_site_settings_compat(request=request, school=school)
    feature = get_effective_feature_control_settings(request=request, school=school)
    offline = get_effective_offline_runtime_settings(request=request, school=school)
    values = {
        "site_name": getattr(site, "site_name", None) if site is not None else None,
        "school_code": getattr(site, "school_code", None) if site is not None else None,
        "tagline": getattr(site, "tagline", None) if site is not None else None,
        "maintenance_mode": getattr(site, "maintenance_mode", None)
        if site is not None
        else None,
        "backend_feature_flags": dict(feature.get("backend_feature_flags") or {}),
        "offline": offline,
    }
    missing = []
    if not values["site_name"]:
        missing.append("Tenant display name")
    if not values["school_code"]:
        missing.append("School code")
    return TenantRuntimeConfig(
        values=values,
        workflow=_workflow(
            is_ready=not missing,
            ready="Tenant runtime configured",
            missing=missing,
            next_step="Complete tenant identity and runtime defaults.",
            url_name="siteconfig:onboarding",
            label="Fix runtime setup",
        ),
    )


def get_modular_configuration_bundle(
    request: Any = None, school: Any = None
) -> ModularConfigurationBundle:
    if school is None and request is not None:
        school = getattr(request, "school", None)
    return ModularConfigurationBundle(
        brand=get_brand_config(request=request, school=school),
        finance=get_finance_config(request=request, school=school),
        payment=get_payment_config(request=request, school=school),
        report=get_report_config(request=request, school=school),
        communication=get_communication_config(request=request, school=school),
        security=get_security_config(request=request, school=school),
        regional=get_regional_config(request=request, school=school),
        marketplace=get_marketplace_config(request=request, school=school),
        tenant_runtime=get_tenant_runtime_config(request=request, school=school),
    )


def _safe_reverse(url_name: str) -> str:
    if not url_name:
        return ""
    try:
        from django.urls import reverse

        return reverse(url_name)
    except Exception:
        return ""


def build_guided_configuration_cards(request: Any = None) -> list[dict[str, Any]]:
    """
    Build operator-facing workflow cards from the modular config bundle.

    Templates consume these dictionaries so they never need to dereference the
    legacy effective settings object directly.
    """
    school = getattr(request, "school", None) if request is not None else None
    bundle = get_modular_configuration_bundle(request=request, school=school)
    cards: list[dict[str, Any]] = []
    for config in bundle.configs:
        workflow = config.workflow
        cards.append(
            {
                "domain": config.key,
                "title": config.label,
                "current_state": workflow.current_state,
                "missing_setup": list(workflow.missing_setup),
                "recommended_next_step": workflow.recommended_next_step,
                "safe_fix_label": workflow.safe_fix_label,
                "safe_fix_url": _safe_reverse(workflow.safe_fix_url_name),
                "value_count": len(config.values),
            }
        )
    return cards
