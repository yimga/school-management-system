"""
Install/uninstall pipeline and widget registry (RunMyCampus blueprint).
On install: record install, apply schema patches if any, register widgets, audit log.
"""
import logging
from django.utils import timezone
from django.core.management import call_command

logger = logging.getLogger(__name__)


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
    except Exception as e:
        logger.warning("Schema patch failed for installation %s (app=%s): %s", installation.id, app_label, e)


def install_app(school, app, *, installed_by=None, config=None, run_schema_patches=True):
    """
    Install an app for a school. Creates AppInstallation, optionally runs schema patches,
    logs audit, returns installation.
    If the app manifest has "migrations_app" or "schema_patch_app" (Django app label),
    and run_schema_patches is True, migrations for that app are run in the current
    connection context (tenant schema in schema-per-tenant mode; single schema in RLS).
    """
    from apps.marketplace.models import AppInstallation, AppAuditLog, MarketplaceApp

    if not isinstance(app, MarketplaceApp):
        app = MarketplaceApp.objects.get(slug=app) if isinstance(app, str) else MarketplaceApp.objects.get(pk=app)
    listing = _assert_app_installable(app)
    installation, created = AppInstallation.objects.get_or_create(
        school=school,
        app=app,
        defaults={
            "status": AppInstallation.Status.ACTIVE,
            "installed_by": installed_by,
            "config": config or {},
            "widget_config": app.manifest.get("widgets", {}),
        },
    )
    if not created:
        installation.status = AppInstallation.Status.ACTIVE
        installation.config = config or installation.config
        installation.widget_config = app.manifest.get("widgets", {})
        installation.save(update_fields=["status", "config", "widget_config"])
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
    except Exception as e:
        logger.warning("Billing record for app install skipped: %s", e)
    return installation


def uninstall_app(school, app, *, uninstalled_by=None):
    """Mark app as uninstalled for the school; audit log."""
    from apps.marketplace.models import AppInstallation, AppAuditLog, MarketplaceApp

    if not isinstance(app, MarketplaceApp):
        app = MarketplaceApp.objects.get(slug=app) if isinstance(app, str) else MarketplaceApp.objects.get(pk=app)
    installation = AppInstallation.objects.get(school=school, app=app)
    installation.status = AppInstallation.Status.UNINSTALLED
    installation.save(update_fields=["status"])
    AppAuditLog.objects.create(
        installation=installation,
        school=school,
        app=app,
        action="uninstall",
        payload={},
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
    scope_codes_or_scope_objects: list of scope_code strings or AppScope instances for this app.
    """
    from apps.marketplace.models import AppScope, ScopeGrant

    for item in scope_codes_or_scope_objects:
        if isinstance(item, AppScope):
            scope = item
        else:
            scope = AppScope.objects.get(app=installation.app, scope_code=item)
        ScopeGrant.objects.get_or_create(
            installation=installation,
            scope=scope,
            defaults={"granted_by": granted_by},
        )


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
