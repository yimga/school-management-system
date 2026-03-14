"""
Install/uninstall pipeline and widget registry (RunMyCampus blueprint).
On install: record install, apply schema patches if any, register widgets, audit log.
"""
import logging
from django.db import DatabaseError, IntegrityError, OperationalError
from django.utils import timezone
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.platform_runtime.structured_logging import log_exception_with_context

logger = logging.getLogger(__name__)

# Typed exceptions for marketplace service paths (compat check, schema patch, billing record).
_MARKETPLACE_COMPAT_ERRORS = (ImportError, AttributeError, TypeError, ValueError, KeyError)
_MARKETPLACE_SCHEMA_BILLING_ERRORS = (
    DatabaseError,
    IntegrityError,
    OperationalError,
    OSError,
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    RuntimeError,
)
_SCHEMA_PATCH_ERRORS = _MARKETPLACE_SCHEMA_BILLING_ERRORS


def ensure_marketplace_listing(app, *, publisher=None):
    from apps.marketplace.models import MarketplaceApp, MarketplaceListing

    if not isinstance(app, MarketplaceApp):
        app = MarketplaceApp.objects.get(slug=app) if isinstance(app, str) else MarketplaceApp.objects.get(pk=app)
    listing, _created = MarketplaceListing.objects.get_or_create(
        app=app,
        defaults={
            "publisher": publisher or app.publisher,
            "short_description": (app.description or "")[:255],
            "status": (
                MarketplaceListing.Status.DRAFT
                if app.kind == MarketplaceApp.AppKind.THIRD_PARTY
                else MarketplaceListing.Status.APPROVED
            ),
            "security_review_status": (
                MarketplaceListing.ReviewStatus.PENDING
                if app.kind == MarketplaceApp.AppKind.THIRD_PARTY
                else MarketplaceListing.ReviewStatus.NOT_REQUIRED
            ),
        },
    )
    changed_fields = []
    if publisher and listing.publisher_id != getattr(publisher, "pk", publisher):
        listing.publisher = publisher
        changed_fields.append("publisher")
    elif listing.publisher_id is None and app.publisher_id:
        listing.publisher = app.publisher
        changed_fields.append("publisher")
    short_description = (app.description or "")[:255]
    if short_description and listing.short_description != short_description:
        listing.short_description = short_description
        changed_fields.append("short_description")
    if changed_fields:
        listing.save(update_fields=changed_fields + ["updated_at"])
    return listing


def check_app_compatibility(school, app, *, warn_only=False):
    """
    Check app/listing compatibility with school (country, blueprint, plan).
    Returns (ok: bool, warnings: list, errors: list).
    If warn_only=True, incompatible returns ok=True with errors in warnings.
    """
    from apps.marketplace.models import MarketplaceApp

    if not isinstance(app, MarketplaceApp):
        app = MarketplaceApp.objects.select_related("listing").get(slug=app) if isinstance(app, str) else MarketplaceApp.objects.select_related("listing").get(pk=app)
    listing = getattr(app, "listing", None)
    if not listing:
        return True, [], []
    compat = getattr(listing, "compatibility", None) or {}
    if not compat:
        return True, [], []
    warnings = []
    errors = []
    # Countries
    countries = compat.get("countries") or compat.get("country_codes")
    if countries and isinstance(countries, (list, tuple)):
        school_country = getattr(school, "country", None) or getattr(school, "country_code", None)
        if school_country and str(school_country).upper() not in [str(c).upper() for c in countries]:
            msg = f"App not declared for country {school_country}"
            if warn_only:
                warnings.append(msg)
            else:
                errors.append(msg)
    # Blueprint families
    blueprint_families = compat.get("blueprint_families")
    if blueprint_families and isinstance(blueprint_families, (list, tuple)):
        try:
            from apps.policies.policy_registry import get_effective_policy
            policy = get_effective_policy(school)
            bp = (policy or {}).get("blueprint") or (policy or {}).get("blueprint_family")
            if bp and str(bp) not in [str(b) for b in blueprint_families]:
                msg = f"App not declared for blueprint family {bp}"
                if warn_only:
                    warnings.append(msg)
                else:
                    errors.append(msg)
        except _MARKETPLACE_COMPAT_ERRORS:
            school_id = getattr(school, "pk", None)
            log_exception_with_context(
                "check_app_compatibility blueprint family check failed",
                school_id=school_id,
                extra={"section": "blueprint_families"},
            )
    # Plan tiers
    plan_tiers = compat.get("plan_tiers")
    if plan_tiers and isinstance(plan_tiers, (list, tuple)):
        school_plan = getattr(school, "plan", None) or getattr(school, "plan_tier", None)
        if school_plan and str(school_plan) not in [str(p) for p in plan_tiers]:
            msg = f"App not declared for plan tier {school_plan}"
            if warn_only:
                warnings.append(msg)
            else:
                errors.append(msg)
    ok = len(errors) == 0
    return ok, warnings, errors


def _assert_app_installable(app):
    from apps.marketplace.models import MarketplaceApp

    if not app.is_active:
        raise ValueError(f"Marketplace app {app.slug} is inactive.")

    listing = getattr(app, "listing", None)
    if listing is None:
        listing = ensure_marketplace_listing(app)

    if app.kind == MarketplaceApp.AppKind.THIRD_PARTY and listing.publisher is None:
        raise ValueError(f"Marketplace app {app.slug} has no verified publisher organization.")
    if listing.kill_switch_active:
        raise ValueError(f"Marketplace app {app.slug} is under platform kill switch.")
    if listing.status != listing.Status.APPROVED:
        raise ValueError(f"Marketplace app {app.slug} is not approved for install.")
    if app.kind == MarketplaceApp.AppKind.THIRD_PARTY and listing.security_review_status != listing.ReviewStatus.APPROVED:
        raise ValueError(f"Marketplace app {app.slug} has not passed security review.")
    return listing


def submit_marketplace_review(
    listing,
    *,
    review_type: str,
    requested_by=None,
    notes: str = "",
    findings_json: dict | None = None,
):
    from apps.marketplace.models import MarketplaceListing, MarketplaceReview

    if not isinstance(listing, MarketplaceListing):
        listing = MarketplaceListing.objects.select_related("app", "publisher").get(pk=listing)

    review = MarketplaceReview.objects.create(
        listing=listing,
        review_type=review_type,
        status=MarketplaceReview.Status.PENDING,
        requested_by=requested_by,
        app_version=listing.app.version,
        notes=notes,
        findings_json=findings_json or {},
    )
    update_fields = []
    if review_type == MarketplaceReview.ReviewType.LISTING and listing.status == MarketplaceListing.Status.DRAFT:
        listing.status = MarketplaceListing.Status.PENDING_REVIEW
        update_fields.append("status")
    if review_type == MarketplaceReview.ReviewType.SECURITY and listing.security_review_status == MarketplaceListing.ReviewStatus.NOT_REQUIRED:
        listing.security_review_status = MarketplaceListing.ReviewStatus.PENDING
        update_fields.append("security_review_status")
    if review_type == MarketplaceReview.ReviewType.CERTIFICATION and listing.certification_status == MarketplaceListing.ReviewStatus.NOT_REQUIRED:
        listing.certification_status = MarketplaceListing.ReviewStatus.PENDING
        update_fields.append("certification_status")
    if update_fields:
        listing.save(update_fields=update_fields + ["updated_at"])
    return review


def finalize_marketplace_review(
    review,
    *,
    status: str,
    reviewed_by=None,
    notes: str = "",
    findings_json: dict | None = None,
):
    from apps.marketplace.models import MarketplaceListing, MarketplaceReview

    if not isinstance(review, MarketplaceReview):
        review = MarketplaceReview.objects.select_related("listing", "listing__app").get(pk=review)
    review.mark_reviewed(
        status=status,
        reviewed_by=reviewed_by,
        notes=notes,
        findings_json=findings_json or review.findings_json,
    )
    listing = review.listing
    update_fields = []
    approved_states = {MarketplaceReview.Status.APPROVED}
    rejected_states = {MarketplaceReview.Status.REJECTED}
    change_states = {MarketplaceReview.Status.CHANGES_REQUIRED}

    if review.review_type == MarketplaceReview.ReviewType.LISTING:
        if status in approved_states:
            listing.status = MarketplaceListing.Status.APPROVED
            listing.approved_at = timezone.now()
            listing.approved_by = reviewed_by
            update_fields.extend(["status", "approved_at", "approved_by"])
        elif status in rejected_states:
            listing.status = MarketplaceListing.Status.REJECTED
            update_fields.append("status")
        elif status in change_states:
            listing.status = MarketplaceListing.Status.DRAFT
            update_fields.append("status")
    elif review.review_type == MarketplaceReview.ReviewType.SECURITY:
        if status in approved_states:
            listing.security_review_status = MarketplaceListing.ReviewStatus.APPROVED
        elif status in rejected_states:
            listing.security_review_status = MarketplaceListing.ReviewStatus.REJECTED
            listing.status = MarketplaceListing.Status.SUSPENDED
            update_fields.append("status")
        elif status in change_states:
            listing.security_review_status = MarketplaceListing.ReviewStatus.CHANGES_REQUIRED
        update_fields.append("security_review_status")
    elif review.review_type == MarketplaceReview.ReviewType.CERTIFICATION:
        if status in approved_states:
            listing.certification_status = MarketplaceListing.ReviewStatus.APPROVED
        elif status in rejected_states:
            listing.certification_status = MarketplaceListing.ReviewStatus.REJECTED
        elif status in change_states:
            listing.certification_status = MarketplaceListing.ReviewStatus.CHANGES_REQUIRED
        update_fields.append("certification_status")
    elif review.review_type == MarketplaceReview.ReviewType.VERSION and status in approved_states:
        listing.metadata = {
            **(listing.metadata or {}),
            "approved_version": review.app_version or listing.app.version,
        }
        update_fields.append("metadata")

    if update_fields:
        listing.save(update_fields=list(dict.fromkeys(update_fields + ["updated_at"])))
    return review, listing


def schedule_publisher_revenue_share_payout(
    listing,
    *,
    gross_amount,
    fee_amount=0,
    source_school=None,
    period_start=None,
    period_end=None,
):
    from apps.billing.models import RevenueSharePayout
    from apps.billing.services import schedule_revenue_share_payout
    from apps.marketplace.models import MarketplaceListing

    if not isinstance(listing, MarketplaceListing):
        listing = MarketplaceListing.objects.select_related("app", "publisher").get(pk=listing)
    publisher = listing.publisher or listing.app.publisher
    if publisher is None:
        raise ValueError("Marketplace listing has no payout-capable publisher.")

    return schedule_revenue_share_payout(
        payee_name=publisher.legal_name or publisher.name,
        gross_amount=gross_amount,
        fee_amount=fee_amount,
        payout_scope=RevenueSharePayout.Scope.APP_PUBLISHER,
        payee_ref=publisher.payout_ref or publisher.slug,
        processor_code=publisher.payout_processor_code,
        currency_code="USD",
        source_school=source_school,
        period_start=period_start,
        period_end=period_end,
        metadata={
            "listing_id": listing.pk,
            "app_slug": listing.app.slug,
            "publisher_slug": publisher.slug,
            "revenue_share_percent": str(listing.revenue_share_percent),
        },
    )


def run_schema_patches_for_installation(installation):
    """
    Run schema patches (migrations) for an app installation when the app manifest
    declares a Django app to migrate (e.g. "migrations_app": "my_app").
    P3: In schema-per-tenant mode, ensures tenant schema is active before running migrate
    (so patches run in the correct tenant schema whether install is from view or task).
    In RLS mode, runs in the single schema. Optional; failures are logged, not raised.
    24.12: Third-party apps: schema patches run only if app_label is in
    THIRD_PARTY_SCHEMA_PATCH_ALLOWLIST (settings). First-party may use any in-repo app label.
    """
    from apps.marketplace.models import AppInstallation, AppAuditLog

    if not isinstance(installation, AppInstallation):
        return
    app = getattr(installation, "app", None)
    if not app:
        return
    manifest = getattr(app, "manifest", None) or {}
    app_label = manifest.get("migrations_app") or manifest.get("schema_patch_app")
    if not app_label or not isinstance(app_label, str):
        return
    app_label = app_label.strip()
    if not app_label:
        return

    # 24.12: Third-party apps have no direct schema freedom; only allowlisted app labels
    from django.conf import settings as django_settings
    from apps.marketplace.models import MarketplaceApp
    if getattr(app, "kind", None) == MarketplaceApp.AppKind.THIRD_PARTY:
        allowlist = getattr(django_settings, "THIRD_PARTY_SCHEMA_PATCH_ALLOWLIST", ())
        if app_label not in (allowlist or []):
            logger.info(
                "Schema patch skipped for third-party app %s: app_label %r not in THIRD_PARTY_SCHEMA_PATCH_ALLOWLIST",
                getattr(app, "slug", app.pk),
                app_label,
            )
            return

    def _run_migrate():
        call_command("migrate", app_label, verbosity=1, run_syncdb=False)

    try:
        school = getattr(installation, "school", None)
        if school:
            from apps.schools.domain_sync import use_django_tenants, ensure_tenant_client_for_school
            if use_django_tenants():
                client = ensure_tenant_client_for_school(school)
                if client and getattr(client, "schema_name", None):
                    from django_tenants.utils import schema_context
                    with schema_context(client.schema_name):
                        _run_migrate()
                else:
                    _run_migrate()
            else:
                _run_migrate()
        else:
            _run_migrate()
        logger.info("Schema patches applied for installation %s (app=%s)", installation.id, app_label)
        AppAuditLog.objects.create(
            installation=installation,
            school=installation.school,
            app=app,
            action="schema_patch",
            payload={"app_label": app_label},
            actor=None,
        )
    except _SCHEMA_PATCH_ERRORS:
        log_exception_with_context(
            "Schema patch failed for installation",
            school_id=getattr(installation, "school_id", None),
            extra={"installation_id": installation.id, "app_label": app_label},
        )


def install_app(school, app, *, installed_by=None, config=None, run_schema_patches=True, install_phase="active", skip_compatibility=False):
    """
    Install an app for a school. Creates AppInstallation, optionally runs schema patches,
    logs audit, returns installation.
    install_phase: "sandbox" or "active". Compatibility is checked unless skip_compatibility=True.
    """
    from apps.marketplace.models import AppInstallation, AppAuditLog, MarketplaceApp

    if not isinstance(app, MarketplaceApp):
        app = MarketplaceApp.objects.get(slug=app) if isinstance(app, str) else MarketplaceApp.objects.get(pk=app)
    if not skip_compatibility:
        ok, _warnings, errors = check_app_compatibility(school, app, warn_only=False)
        if not ok and errors:
            raise ValueError(f"App incompatible: {'; '.join(errors)}")
    listing = _assert_app_installable(app)
    phase = install_phase if install_phase in ("sandbox", "active") else "active"
    installation, created = AppInstallation.objects.get_or_create(
        school=school,
        app=app,
        defaults={
            "status": AppInstallation.Status.ACTIVE,
            "install_phase": phase,
            "installed_by": installed_by,
            "config": config or {},
            "widget_config": app.manifest.get("widgets", {}),
        },
    )
    if not created:
        installation.status = AppInstallation.Status.ACTIVE
        installation.install_phase = phase
        installation.config = config or installation.config
        installation.widget_config = app.manifest.get("widgets", {})
        installation.save(update_fields=["status", "install_phase", "config", "widget_config"])
    if run_schema_patches:
        run_schema_patches_for_installation(installation)
    AppAuditLog.objects.create(
        installation=installation,
        school=school,
        app=app,
        action="install",
        payload={
            "config": installation.config,
            "listing_status": getattr(listing, "status", ""),
            "publisher": getattr(getattr(listing, "publisher", None), "slug", ""),
        },
        actor=installed_by,
    )
    # 6.3 / 29.10: Record app install for billing (ledger line; optional add-on pricing later)
    try:
        from apps.billing.services import record_app_install_for_billing
        record_app_install_for_billing(school, app, installation)
    except _MARKETPLACE_SCHEMA_BILLING_ERRORS as e:
        school_id = getattr(school, "pk", None)
        log_exception_with_context(
            "Billing record for app install skipped",
            school_id=school_id,
            extra={"app_slug": getattr(app, "slug", None), "installation_id": getattr(installation, "id", None)},
        )
        logger.warning("Billing record for app install skipped: %s", e)
    return installation


def uninstall_app(school, app, *, uninstalled_by=None, run_cleanup=True):
    """
    Mark app as uninstalled for the school; set uninstalled_at; audit log.
    If run_cleanup and app manifest has uninstall_cleanup (e.g. retention_days), log for async cleanup.
    """
    from apps.marketplace.models import AppInstallation, AppAuditLog, MarketplaceApp

    if not isinstance(app, MarketplaceApp):
        app = MarketplaceApp.objects.get(slug=app) if isinstance(app, str) else MarketplaceApp.objects.get(pk=app)
    installation = AppInstallation.objects.get(school=school, app=app)
    installation.status = AppInstallation.Status.UNINSTALLED
    installation.uninstalled_at = timezone.now()
    installation.save(update_fields=["status", "uninstalled_at"])
    cleanup_policy = (app.manifest or {}).get("uninstall_cleanup") or {}
    payload = {"uninstalled_at": str(installation.uninstalled_at)}
    if run_cleanup and cleanup_policy:
        payload["cleanup_policy"] = cleanup_policy
        payload["cleanup_deferred"] = True
    AppAuditLog.objects.create(
        installation=installation,
        school=school,
        app=app,
        action="uninstall",
        payload=payload,
        actor=uninstalled_by,
    )
    return installation


def suspend_app(school, app, *, suspended_by=None, reason: str = ""):
    """
    Kill switch (A2): suspend an app for a school. Widgets and capabilities are no longer served.
    get_installed_widgets already filters status=ACTIVE, so suspended apps are excluded.
    """
    from apps.marketplace.models import AppInstallation, AppAuditLog, MarketplaceApp

    if not isinstance(app, MarketplaceApp):
        app = MarketplaceApp.objects.get(slug=app) if isinstance(app, str) else MarketplaceApp.objects.get(pk=app)
    installation = AppInstallation.objects.get(school=school, app=app)
    installation.status = AppInstallation.Status.SUSPENDED
    installation.save(update_fields=["status"])
    AppAuditLog.objects.create(
        installation=installation,
        school=school,
        app=app,
        action="suspend",
        payload={"reason": reason or ""},
        actor=suspended_by,
    )
    return installation


def unsuspend_app(school, app, *, unsuspended_by=None):
    """Re-enable a suspended app for the school."""
    from apps.marketplace.models import AppInstallation, AppAuditLog, MarketplaceApp

    if not isinstance(app, MarketplaceApp):
        app = MarketplaceApp.objects.get(slug=app) if isinstance(app, str) else MarketplaceApp.objects.get(pk=app)
    installation = AppInstallation.objects.get(school=school, app=app)
    installation.status = AppInstallation.Status.ACTIVE
    installation.save(update_fields=["status"])
    AppAuditLog.objects.create(
        installation=installation,
        school=school,
        app=app,
        action="unsuspend",
        payload={},
        actor=unsuspended_by,
    )
    return installation


def grant_scopes(installation, scope_codes_or_scope_objects, granted_by=None):
    """
    Grant one or more scopes to an installation (tenant-approved). Creates ScopeGrant records.
    Sensitive scopes get status=pending until elevated_approved_by is set.
    """
    from apps.marketplace.models import AppScope, ScopeGrant

    for item in scope_codes_or_scope_objects:
        if isinstance(item, AppScope):
            scope = item
        else:
            scope = AppScope.objects.get(app=installation.app, scope_code=item)
        status = ScopeGrant.GrantStatus.PENDING if getattr(scope, "sensitive", False) else ScopeGrant.GrantStatus.GRANTED
        ScopeGrant.objects.get_or_create(
            installation=installation,
            scope=scope,
            defaults={"granted_by": granted_by, "status": status},
        )


def approve_sensitive_scope(scope_grant, approved_by):
    """Set scope grant to granted and set elevated_approved_at/by. Idempotent."""
    from apps.marketplace.models import ScopeGrant

    if not isinstance(scope_grant, ScopeGrant):
        scope_grant = ScopeGrant.objects.select_related("scope").get(pk=scope_grant)
    scope_grant.status = ScopeGrant.GrantStatus.GRANTED
    scope_grant.elevated_approved_at = timezone.now()
    scope_grant.elevated_approved_by = approved_by
    scope_grant.save(update_fields=["status", "elevated_approved_at", "elevated_approved_by"])
    return scope_grant


def activate_sandbox_installation(installation, activated_by=None):
    """Move installation from sandbox to active so it appears in runtime."""
    from apps.marketplace.models import AppInstallation, AppAuditLog

    installation.install_phase = AppInstallation.InstallPhase.ACTIVE
    installation.save(update_fields=["install_phase"])
    AppAuditLog.objects.create(
        installation=installation,
        school=installation.school,
        app=installation.app,
        action="activate_sandbox",
        payload={},
        actor=activated_by,
    )
    return installation


def record_installation_health(installation, status: str = "ok"):
    """Update last_health_at and health_status for monitoring."""
    installation.last_health_at = timezone.now()
    installation.health_status = status
    installation.save(update_fields=["last_health_at", "health_status"])


def refresh_installation(installation):
    """
    Re-apply app manifest to installation (e.g. widget_config from app.manifest).
    Use after app version update to sync widget_config and other manifest-derived fields.
    """
    app = installation.app
    manifest = getattr(app, "manifest", None) or {}
    widgets = manifest.get("widgets") or {}
    if isinstance(widgets, dict):
        installation.widget_config = widgets
        installation.save(update_fields=["widget_config"])
    return installation


def get_installed_widgets(school):
    """
    Return list of widget configs for active installations (for dashboard/portal injection).
    Each item: { "app_slug": ..., "widget_id": ..., "config": ... } from manifest + widget_config.
    """
    from apps.marketplace.models import AppInstallation

    widgets = []
    for inst in AppInstallation.objects.filter(school=school, status=AppInstallation.Status.ACTIVE).select_related(
        "app"
    ):
        wconfig = inst.widget_config or inst.app.manifest.get("widgets") or {}
        if isinstance(wconfig, dict):
            for widget_id, cfg in wconfig.items():
                widgets.append({
                    "app_slug": inst.app.slug,
                    "widget_id": widget_id,
                    "config": cfg if isinstance(cfg, dict) else {},
                })
        elif isinstance(wconfig, list):
            for w in wconfig:
                widgets.append({
                    "app_slug": inst.app.slug,
                    "widget_id": w.get("id", ""),
                    "config": w,
                })
    return widgets
