"""Tenant + operator Migration Cloud connector wizard views."""

from __future__ import annotations

import logging
from uuid import UUID

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.views.generic import TemplateView

from apps.accounts.decorators import user_is_tenant_admin

from .models_connectors import (
    ConnectionMethod,
    CredentialStorageMode,
    MigrationConnectorProfile,
    MigrationDiscoveryRun,
    MigrationImportRun,
    MigrationSourceConnection,
    MigrationStagingBatch,
    SourceConnectionStatus,
)
from .services.connector_credentials import (
    create_source_connection,
    purge_source_credentials,
    redact_connection_for_display,
    revoke_source_connection,
    store_source_credential_reference,
    verify_source_authorization,
)
from .services.connector_discovery import (
    fetch_sample_records,
    run_source_discovery,
    stage_entity_preview,
)
from .services.connector_import import generate_idempotency_key, run_connector_import
from .services.connector_mapping import confirm_mappings, suggest_field_mappings
from .services.connector_rollback import rollback_posture_card

logger = logging.getLogger(__name__)


def _request_school(request: HttpRequest):
    school = getattr(request, "school", None) or getattr(request, "tenant", None)
    if school is not None:
        return school
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    membership_mgr = getattr(user, "school_memberships", None)
    if membership_mgr is None:
        return None
    # tenant-isolation-allow: connector-wizard-resolve-school-via-membership
    membership = membership_mgr.select_related("school").first()
    return getattr(membership, "school", None) if membership else None


class _ConnectorTenantAdminRequiredMixin(LoginRequiredMixin):
    """Gate a connector-wizard surface on the tenant-admin tier of the request's school.

    The wizard is TENANT-HOST-ONLY (config/tenant_urls.py) and drives imports that
    overwrite the school's live data, so ``LoginRequiredMixin`` alone — which SAML/SCIM
    satisfies for EVERY provisioned member — let any teacher / parent / student POST a
    connect / discover / import / revoke. Require the tenant-admin tier of the request's
    OWN school (owner / role=ADMIN / settings.manage + audited superuser break-glass) via
    the canonical :func:`apps.accounts.decorators.user_is_tenant_admin`, mirroring the
    file-upload flow's ``_TenantAdminWriteRequiredMixin``. Blocks GET too — a plain member
    has no business in the migration connector at all. (Defined locally rather than
    imported from ``views_tenant_upload`` because that module imports ``_request_school``
    from HERE; a module-level import back would be circular.)
    """

    def dispatch(self, request, *args, **kwargs):
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False) and not user_is_tenant_admin(
            user, _request_school(request)
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def _resolve_connector_upload_url(request: HttpRequest) -> str:
    """Host-aware target for the connector "Upload export file" CTA.

    The connector home renders on THREE hosts — the tenant host
    (``migration_cloud_connector``) and the two operator mounts
    (``migration_cloud_portal`` under config.urls, ``migration_cloud_super``
    under manager_urls). A hardcoded ``{% url %}`` to any single namespace
    ``NoReverseMatch``-es on the other two (that was the cross-host 500). Resolve
    against the request's active urlconf, preferring the operator bundle-intake
    wizard when mounted under it, else the tenant import hub, else the connector
    connect step. Returns "" if nothing resolves (the button then hides).
    """
    resolver_match = getattr(request, "resolver_match", None)
    namespaces = list(getattr(resolver_match, "namespaces", []) or [])
    # On the tenant host (neither operator mount present) prefer the connectionless
    # in-place uploader — drop a file, auto-detect entity + format, no connection.
    # Operator / portal mounts keep their full bundle-intake wizard (bundle_new).
    if "migration_cloud_super" not in namespaces and "migration_cloud_portal" not in namespaces:
        try:
            return _connector_reverse(request, "upload")
        except NoReverseMatch:
            pass
    candidates: list[str] = []
    if "migration_cloud_super" in namespaces:
        candidates.append("migration_cloud_super:bundle_new")
    if "migration_cloud_portal" in namespaces:
        candidates.append("migration_cloud_portal:bundle_new")
    candidates.append("school_setup_imports")  # tenant host import hub
    candidates.append("migration_cloud_connector:connector-connect")  # universal fallback
    for name in candidates:
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    return ""


def _connector_namespace(request: HttpRequest) -> str:
    """Fully-qualified namespace for connector wizard URLs on the active mount.

    ``urls_connectors`` is included as ``migration_cloud_connector``, but that
    include lives inside ``apps.migration_cloud.urls`` — itself mounted under
    ``migration_cloud_super`` (operator) and ``migration_cloud_portal`` (portal)
    as well as standalone on the tenant host. So the real namespace is
    ``migration_cloud_super:migration_cloud_connector`` on the operator mount, etc.
    A bare ``migration_cloud_connector:<name>`` reverse NoReverseMatch-es → 500 on
    the nested mounts (the same failure ``_resolve_connector_upload_url`` guards).
    ``resolver_match.namespaces`` already carries the full chain (its last element
    is ``migration_cloud_connector`` for a wizard view); join it to rebuild the
    prefix. Falls back to the tenant-host top-level namespace.
    """
    resolver_match = getattr(request, "resolver_match", None)
    namespaces = list(getattr(resolver_match, "namespaces", []) or [])
    if namespaces and namespaces[-1] == "migration_cloud_connector":
        return ":".join(namespaces)
    return "migration_cloud_connector"


def _connector_reverse(request: HttpRequest, name: str, **kwargs) -> str:
    """reverse() a connector wizard URL name under the request's active namespace.

    Mount-agnostic stand-in for ``reverse("migration_cloud_connector:<name>")`` so
    wizard redirects resolve on the operator/portal mounts, not just the tenant host.
    """
    try:
        return reverse(f"{_connector_namespace(request)}:{name}", kwargs=kwargs)
    except NoReverseMatch:
        return reverse(f"migration_cloud_connector:{name}", kwargs=kwargs)


def _resolve_connector_inbox_url(request: HttpRequest) -> str:
    """Host-aware target for the "See all imports" CTA, or "" if not mounted.

    Same cross-host hazard as :func:`_resolve_connector_upload_url`: the connector
    home renders on the tenant host and both operator mounts, so the inbox link is
    resolved against the request's active urlconf rather than hardcoded. Returning
    "" simply hides the button instead of 500-ing a mount that lacks the route.
    """
    try:
        return _connector_reverse(request, "migration-inbox")
    except NoReverseMatch:
        return ""


def _connection_for_request(request: HttpRequest, connection_id: UUID) -> MigrationSourceConnection:
    school = _request_school(request)
    if school is None:
        raise Http404()
    # tenant-isolation-allow: connector-wizard-scoped-by-school-fk
    return get_object_or_404(
        MigrationSourceConnection.objects.select_related("connector_profile"),
        id=connection_id,
        school=school,
    )


def _friendly_import_error(code: str) -> str:
    """Turn a ``run_connector_import`` ValueError code into an operator message."""
    if code.startswith("import_blocked_unmapped_required:"):
        fields = code.split(":", 1)[1]
        return f"Map the required destination field(s) before importing: {fields}."
    return {
        "import_blocked_no_rows": (
            "No source records were discovered for this connection, so there is "
            "nothing to import. Upload an export file, or run discovery against a "
            "source that returns data, then try again."
        ),
        "import_blocked_data_quality_threshold": (
            "The data quality score is below the safe import threshold. Resolve the "
            "quarantined rows, or tick “Import anyway” to override."
        ),
        "import_requires_verified_connection": (
            "This connection is not verified yet. Re-connect and confirm "
            "authorization before importing."
        ),
        "import_requires_authorization": (
            "Authorization has not been confirmed for this connection."
        ),
    }.get(code, "The import could not be started. Review the connection and try again.")


class MigrationCloudConnectorHomeView(_ConnectorTenantAdminRequiredMixin, TemplateView):
    template_name = "migration_cloud/connector/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        school = _request_school(self.request)
        if school is None:
            raise Http404()
        # tenant-isolation-allow: connector-home-list-for-tenant-school
        connections = MigrationSourceConnection.objects.filter(school=school).select_related(
            "connector_profile"
        )[:50]
        profiles = MigrationConnectorProfile.objects.filter(active=True)
        ctx.update(
            {
                "page_title": "Migration Cloud",
                "connections": connections,
                "profiles": profiles,
                "school": school,
                "upload_url": _resolve_connector_upload_url(self.request),
                "inbox_url": _resolve_connector_inbox_url(self.request),
                "connector_ns": _connector_namespace(self.request),
            }
        )
        return ctx


@method_decorator(csrf_protect, name="dispatch")
class MigrationCloudConnectorConnectView(_ConnectorTenantAdminRequiredMixin, View):
    template_name = "migration_cloud/connector/connect.html"

    def get(self, request: HttpRequest, **kwargs) -> HttpResponse:
        school = _request_school(request)
        if school is None:
            raise Http404()
        profiles = MigrationConnectorProfile.objects.filter(active=True)
        return render(
            request,
            self.template_name,
            {
                "page_title": "Connect source platform",
                "profiles": profiles,
                "connection_methods": ConnectionMethod.choices,
                "storage_modes": CredentialStorageMode.choices,
            },
        )

    def post(self, request: HttpRequest, **kwargs) -> HttpResponse:
        school = _request_school(request)
        if school is None:
            raise Http404()
        profile_key = request.POST.get("profile_key", "")
        profile = get_object_or_404(MigrationConnectorProfile, key=profile_key, active=True)
        storage_mode = request.POST.get(
            "credential_storage_mode", CredentialStorageMode.MEMORY_ONLY
        )
        connection = create_source_connection(
            school=school,
            created_by=request.user,
            connector_profile=profile,
            source_platform_type=profile.key,
            source_url=request.POST.get("source_url", "").strip(),
            connection_method=request.POST.get("connection_method", ConnectionMethod.FILE_EXPORT),
            credential_storage_mode=storage_mode,
            notes=request.POST.get("notes", ""),
        )
        creds = {}
        if request.POST.get("api_token"):
            creds["api_token"] = request.POST.get("api_token")
        if request.POST.get("username"):
            creds["username"] = request.POST.get("username")
        if request.POST.get("password"):
            creds["password"] = request.POST.get("password")
        if creds:
            store_source_credential_reference(connection, credential_payload=creds)

        if request.POST.get("authorization_confirmed") == "on":
            connection.authorization_confirmed = True
            connection.authorization_confirmed_by = request.user
            connection.terms_acknowledged = request.POST.get("terms_acknowledged") == "on"
            from django.utils import timezone

            connection.authorization_confirmed_at = timezone.now()
            connection.save(
                update_fields=[
                    "authorization_confirmed",
                    "authorization_confirmed_by",
                    "authorization_confirmed_at",
                    "terms_acknowledged",
                    "updated_at",
                ]
            )
            verify_source_authorization(connection)

        return redirect(
            _connector_reverse(request, "connector-discover", connection_id=connection.id)
        )


class MigrationCloudConnectorDiscoverView(_ConnectorTenantAdminRequiredMixin, View):
    template_name = "migration_cloud/connector/discover.html"

    def get(self, request: HttpRequest, connection_id: UUID, **kwargs) -> HttpResponse:
        connection = _connection_for_request(request, connection_id)
        runs = connection.discovery_runs.order_by("-started_at")[:5]
        return render(
            request,
            self.template_name,
            {
                "page_title": "Discover data",
                "connection": connection,
                "connection_display": redact_connection_for_display(connection),
                "discovery_runs": runs,
            },
        )

    def post(self, request: HttpRequest, connection_id: UUID, **kwargs) -> HttpResponse:
        connection = _connection_for_request(request, connection_id)
        if connection.status != SourceConnectionStatus.VERIFIED:
            # A DRAFT/REVOKED/FAILED connection is still linked from the home
            # list; running discovery on it raises. Re-render with guidance
            # instead of a 500.
            return render(
                request,
                self.template_name,
                {
                    "page_title": "Discover data",
                    "connection": connection,
                    "connection_display": redact_connection_for_display(connection),
                    "discovery_runs": connection.discovery_runs.order_by("-started_at")[:5],
                    "discover_error": (
                        "This connection is not verified yet. Go back and confirm "
                        "authorization before running discovery."
                    ),
                },
            )
        run = run_source_discovery(connection=connection, started_by=request.user)
        return redirect(
            _connector_reverse(
                request, "connector-mapping", connection_id=connection.id, run_id=run.id
            )
        )


class MigrationCloudConnectorMappingView(_ConnectorTenantAdminRequiredMixin, View):
    template_name = "migration_cloud/connector/mapping.html"

    def get(self, request: HttpRequest, connection_id: UUID, run_id: UUID, **kwargs) -> HttpResponse:
        connection = _connection_for_request(request, connection_id)
        discovery_run = get_object_or_404(
            MigrationDiscoveryRun,
            id=run_id,
            school=connection.school,
            source_connection=connection,
        )
        entity = request.GET.get("entity", "students")
        # Derive the source columns from real discovered sample rows so the
        # suggested mapping reflects the actual export, not a hardcoded stub.
        sample_rows = fetch_sample_records(connection=connection, entity_type=entity)
        source_fields = sorted({key for row in sample_rows for key in row.keys()})
        mappings = suggest_field_mappings(
            connection=connection,
            entity_type=entity,
            source_fields=source_fields or ["admission_number", "first_name", "last_name"],
            actor=request.user,
        )
        return render(
            request,
            self.template_name,
            {
                "page_title": "Map fields",
                "connection": connection,
                "discovery_run": discovery_run,
                "entity_type": entity,
                "mappings": mappings,
            },
        )

    def post(self, request: HttpRequest, connection_id: UUID, run_id: UUID, **kwargs) -> HttpResponse:
        connection = _connection_for_request(request, connection_id)
        entity = request.POST.get("entity_type", "students")
        confirm_mappings(connection=connection, entity_type=entity, actor=request.user)
        return redirect(
            _connector_reverse(
                request, "connector-validate", connection_id=connection.id, run_id=run_id
            )
        )


class MigrationCloudConnectorValidateView(_ConnectorTenantAdminRequiredMixin, View):
    template_name = "migration_cloud/connector/validate.html"

    def get(self, request: HttpRequest, connection_id: UUID, run_id: UUID, **kwargs) -> HttpResponse:
        connection = _connection_for_request(request, connection_id)
        discovery_run = get_object_or_404(
            MigrationDiscoveryRun,
            id=run_id,
            school=connection.school,
            source_connection=connection,
        )
        entity = request.GET.get("entity", "students")
        # Idempotent: reuse the batch already staged for this run+entity so a
        # page refresh (a GET) does not spawn a new empty batch every time.
        batch = (
            MigrationStagingBatch.objects.filter(
                school=connection.school,
                source_connection=connection,
                discovery_run=discovery_run,
                entity_type=entity,
            )
            .order_by("-created_at")
            .first()
        )
        if batch is None:
            # Stage the real discovered sample rows (empty when the source has
            # no export attached — the import step then blocks with guidance
            # rather than importing nothing).
            rows = fetch_sample_records(connection=connection, entity_type=entity)
            batch, quarantine = stage_entity_preview(
                connection=connection,
                discovery_run=discovery_run,
                entity_type=entity,
                rows=rows,
            )
        else:
            quarantine = list(batch.quarantine_items.all())
        return render(
            request,
            self.template_name,
            {
                "page_title": "Validate data quality",
                "connection": connection,
                "discovery_run": discovery_run,
                "staging_batch": batch,
                "quarantine_items": quarantine,
                "data_quality_score": batch.data_quality_score,
                "connector_ns": _connector_namespace(request),
            },
        )


class MigrationCloudConnectorQuarantineView(_ConnectorTenantAdminRequiredMixin, TemplateView):
    template_name = "migration_cloud/connector/quarantine.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        connection = _connection_for_request(self.request, kwargs["connection_id"])
        batch = get_object_or_404(
            MigrationStagingBatch,
            id=kwargs["batch_id"],
            school=connection.school,
            source_connection=connection,
        )
        ctx.update(
            {
                "connection": connection,
                "staging_batch": batch,
                "quarantine_items": batch.quarantine_items.all()[:100],
            }
        )
        return ctx


class MigrationCloudConnectorImportView(_ConnectorTenantAdminRequiredMixin, View):
    template_name = "migration_cloud/connector/import.html"

    def get(self, request: HttpRequest, connection_id: UUID, batch_id: UUID, **kwargs) -> HttpResponse:
        connection = _connection_for_request(request, connection_id)
        batch = get_object_or_404(
            MigrationStagingBatch,
            id=batch_id,
            school=connection.school,
            source_connection=connection,
        )
        return render(
            request,
            self.template_name,
            {
                "page_title": "Confirm import",
                "connection": connection,
                "staging_batch": batch,
                "idempotency_key": generate_idempotency_key(),
            },
        )

    def post(self, request: HttpRequest, connection_id: UUID, batch_id: UUID, **kwargs) -> HttpResponse:
        connection = _connection_for_request(request, connection_id)
        batch = get_object_or_404(
            MigrationStagingBatch,
            id=batch_id,
            school=connection.school,
            source_connection=connection,
        )
        try:
            import_run = run_connector_import(
                connection=connection,
                staging_batch=batch,
                started_by=request.user,
                idempotency_key=request.POST.get("idempotency_key"),
                quality_override=request.POST.get("quality_override") == "on",
                off_http=True,
            )
        except ValueError as exc:
            # Blocked-import conditions (no rows, quality below threshold,
            # unmapped required, unverified) are expected outcomes, not 500s.
            logger.info(
                "connector_import blocked connection=%s reason=%s",
                str(connection.id)[:8],
                str(exc)[:60],
            )
            return render(
                request,
                self.template_name,
                {
                    "page_title": "Confirm import",
                    "connection": connection,
                    "staging_batch": batch,
                    "idempotency_key": (
                        request.POST.get("idempotency_key") or generate_idempotency_key()
                    ),
                    "import_error": _friendly_import_error(str(exc)),
                },
            )
        return redirect(
            _connector_reverse(
                request,
                "connector-review",
                connection_id=connection.id,
                import_run_id=import_run.id,
            )
        )


class MigrationCloudConnectorReviewView(_ConnectorTenantAdminRequiredMixin, TemplateView):
    template_name = "migration_cloud/connector/review.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        connection = _connection_for_request(self.request, kwargs["connection_id"])
        import_run = get_object_or_404(
            MigrationImportRun,
            id=kwargs["import_run_id"],
            school=connection.school,
        )
        ctx.update(
            {
                "connection": connection,
                "import_run": import_run,
                "rollback_card": rollback_posture_card(import_run),
                "audit_events": connection.audit_events.order_by("-created_at")[:20],
                "connector_ns": _connector_namespace(self.request),
            }
        )
        return ctx


@method_decorator(csrf_protect, name="dispatch")
class MigrationCloudConnectorRevokeView(_ConnectorTenantAdminRequiredMixin, View):
    def post(self, request: HttpRequest, connection_id: UUID, **kwargs) -> HttpResponse:
        connection = _connection_for_request(request, connection_id)
        revoke_source_connection(connection)
        purge_source_credentials(connection)
        return redirect(_connector_reverse(request, "connector-home"))


class MigrationCloudConnectorOperatorView(LoginRequiredMixin, TemplateView):
    """Operator control plane — staff only."""

    template_name = "migration_cloud/connector/operator.html"

    def dispatch(self, request, *args, **kwargs):
        # is_staff is NOT an operator signal — the platform mints is_staff=True
        # tenant admins, so keying this cross-tenant operator dashboard on is_staff
        # let any tenant admin read every school's connections + imports. Gate on
        # genuine control-plane access (the predicate the API layer already uses).
        from apps.schools.control_plane import user_has_control_plane_access

        if not user_has_control_plane_access(getattr(request, "user", None)):
            raise Http404()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "page_title": "Migration Cloud — Operator",
                # tenant-isolation-allow: control-plane-operator-dashboard-cross-tenant-review
                "active_connections": MigrationSourceConnection.objects.filter(
                    status=SourceConnectionStatus.VERIFIED
                ).select_related("school", "connector_profile")[:50],
                # tenant-isolation-allow: control-plane-operator-dashboard-cross-tenant-review
                "failed_connections": MigrationSourceConnection.objects.filter(
                    status=SourceConnectionStatus.FAILED
                )[:20],
                "profiles": MigrationConnectorProfile.objects.filter(active=True),
                "recent_imports": MigrationImportRun.objects.select_related("school").order_by(
                    "-started_at"
                )[:30],
            }
        )
        return ctx
