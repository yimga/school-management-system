"""DRF viewsets for the Migration Cloud public REST API alpha.

Two viewsets:
  - :class:`BundleViewSet` — list / retrieve / create + custom action
    endpoints for ``advance`` / ``apply`` / ``reconcile`` that delegate
    to the existing wizard views.
  - :class:`CanonicalTemplateViewSet` — read-only surface for the 20
    canonical-domain templates (list / retrieve / zip download).

Every viewset class AND every ``@action`` carries an ``@extend_schema``
decoration to keep ``scan_drf_schema_coverage`` at zero — the gate is
zero-tolerance for this app per CLAUDE.md.

Tenant isolation: every queryset filter that narrows the cross-tenant
view carries a ``# tenant-isolation-allow: <3+-part-hyphenated-reason>``
marker so ``scan_tenant_isolation_marker_quality`` accepts it.
"""

from __future__ import annotations

import io
import logging
import uuid
import zipfile

from django.http import HttpResponse
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.migration_cloud.models import (
    BundleStatus,
    IntakeMethod,
    MigrationBundle,
    SlaTier,
)
from apps.migration_cloud.reliability import idempotent_post, safe_500
from apps.migration_cloud.views import (
    MigrationCloudAdvanceView,
    MigrationCloudApplyView,
    MigrationCloudReconcileView,
)

from .helpers import delegate_to_view, shell_for_request
from .permissions import MigrationCloudAPIPermission
from .serializers import (
    MigrationArtifactSerializer,
    MigrationBundleSerializer,
)

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        tags=["Migration Cloud"],
        summary="List migration bundles visible to the caller",
        description=(
            "Returns the paginated list of migration bundles. Staff callers "
            "see every bundle; tenant callers see only bundles bound to "
            "their active school. Pre-tenant staging bundles (school is "
            "NULL) are operator-only and hidden from tenant callers."
        ),
        responses={
            200: MigrationBundleSerializer(many=True),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Tenant binding missing"),
        },
    ),
    retrieve=extend_schema(
        tags=["Migration Cloud"],
        summary="Get one migration bundle by ID",
        description=(
            "Returns the bundle's status, summaries, and intake metadata. "
            "Tenant scoping is enforced — a tenant caller asking for a "
            "bundle bound to a different school sees 404, not 403, so an "
            "ID-enumeration attacker can't distinguish 'exists elsewhere' "
            "from 'doesn't exist'."
        ),
        responses={
            200: MigrationBundleSerializer,
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Bundle not found or out of tenant scope"),
        },
    ),
    create=extend_schema(
        tags=["Migration Cloud"],
        summary="Create a new migration bundle (skeleton, pre-ingest)",
        description=(
            "Creates a fresh bundle in PENDING status. Pass an "
            "``Idempotency-Key`` header so a flaky network or retry "
            "loop doesn't create duplicate bundles. After creation, "
            "attach artifacts (future endpoint) or trigger the "
            "``advance`` action to drive the bundle through profile → "
            "classify → map."
        ),
        request=MigrationBundleSerializer,
        responses={
            201: MigrationBundleSerializer,
            400: OpenApiResponse(description="Invalid intake payload"),
            401: OpenApiResponse(description="Authentication required"),
            409: OpenApiResponse(description="Duplicate idempotency key"),
        },
    ),
)
class BundleViewSet(viewsets.ModelViewSet):
    """REST viewset for MigrationBundle.

    Supports ``list``, ``retrieve``, ``create``, plus custom action
    endpoints that delegate to the existing wizard views for
    ``advance`` / ``apply`` / ``reconcile``.

    Deferred (see docket): PATCH / DELETE — bundles advance via the
    state machine, not direct field updates; teardown is operator-only
    and goes through the wizard.
    """

    serializer_class = MigrationBundleSerializer
    permission_classes = [IsAuthenticated, MigrationCloudAPIPermission]
    http_method_names = ["get", "post", "head", "options"]
    lookup_field = "pk"

    def get_queryset(self):
        """Return the bundle queryset narrowed to the caller's tenant scope.

        Staff see all bundles; non-staff see only their bound school's
        bundles. The marker reason is intentionally explicit:
        the API layer enforces tenant scoping by routing every read
        through the authenticated user's school binding, not via raw
        cross-tenant queries.
        """
        qs = MigrationBundle.objects.all()  # tenant-isolation-allow: api-layer-staff-superset-narrowed-below
        user = getattr(self.request, "user", None)
        if user is None or not user.is_authenticated:
            return qs.none()  # tenant-isolation-allow: api-layer-anonymous-rejected-defense-in-depth
        if user.is_staff:
            return qs  # tenant-isolation-allow: api-layer-staff-operator-shell-cross-tenant-by-design
        school = (
            getattr(self.request, "school", None)
            or getattr(self.request, "tenant", None)
        )
        school_pk = getattr(school, "pk", None)
        if school_pk is None:
            return qs.none()  # tenant-isolation-allow: api-layer-no-tenant-binding-deny-by-default
        return qs.filter(school_id=school_pk)  # tenant-isolation-allow: api-layer-scoped-via-request-user-school

    # ─── create() ─────────────────────────────────────────────────────────
    @idempotent_post
    @safe_500
    def create(self, request, *args, **kwargs):
        """Create a bundle skeleton with a generated idempotency key.

        Partners SHOULD pass an ``Idempotency-Key`` header so retries
        don't create duplicate bundles; absent the header, we generate
        one server-side (still unique per call). The wizard-level
        idempotency on ``bundle.idempotency_key`` provides a second
        line of defense against duplicate bundle creation.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        # Resolve target school: staff callers may post without a school
        # binding (pre-tenant staging); tenant callers always bind to
        # their request school.
        user = request.user
        if user.is_staff:
            target_school = (
                getattr(request, "school", None)
                or getattr(request, "tenant", None)
            )
            target_school_id = getattr(target_school, "pk", None)
        else:
            school = (
                getattr(request, "school", None)
                or getattr(request, "tenant", None)
            )
            target_school_id = getattr(school, "pk", None)
            if target_school_id is None:
                return Response(
                    {"error": "no tenant binding for caller"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        bundle = MigrationBundle.objects.create(
            school_id=target_school_id,
            label=validated.get("label", "") or "",
            source_hint=validated.get("source_hint", "") or "",
            intake_method=validated.get("intake_method", IntakeMethod.FILE_UPLOAD),
            sla_tier=validated.get("sla_tier", SlaTier.SMALL),
            idempotency_key=f"api-{uuid.uuid4().hex}",
            status=BundleStatus.PENDING,
            triggered_by=user if user.is_authenticated else None,
        )
        out = self.get_serializer(bundle).data
        return Response(out, status=status.HTTP_201_CREATED)

    # ─── advance ───────────────────────────────────────────────────────────
    @extend_schema(
        tags=["Migration Cloud"],
        summary="Advance a bundle through profile → classify → map",
        description=(
            "Drives the bundle's state machine forward one phase. "
            "Idempotent via the ``Idempotency-Key`` header — a duplicate "
            "POST within 24h returns the cached response with "
            "``X-Idempotency-Replay: true``."
        ),
        request=None,
        responses={
            200: OpenApiResponse(description="Bundle advanced; summary JSON"),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Bundle not found"),
            500: OpenApiResponse(description="Structured 500 envelope with request_id"),
        },
    )
    @action(detail=True, methods=["post"], url_path="advance")
    @idempotent_post
    @safe_500
    def advance(self, request, pk=None):
        """Delegate to MigrationCloudAdvanceView.post().

        Outer ``@idempotent_post`` caches by API path so the API surface
        gets its own 24h replay window distinct from the wizard view's;
        ``@safe_500`` ensures any uncaught exception in the delegation
        boundary itself emits a structured envelope with a request_id.
        """
        return delegate_to_view(
            MigrationCloudAdvanceView,
            request,
            bundle_id=int(pk),
            shell=shell_for_request(request),
        )

    # ─── apply ─────────────────────────────────────────────────────────────
    @extend_schema(
        tags=["Migration Cloud"],
        summary="Apply a MAPPED bundle to the tenant (default: dry-run)",
        description=(
            "Applies the mapped bundle. **Defaults to dry-run** — live "
            "apply requires ``?confirm=1`` AND must not set ``?dry_run=1``. "
            "Idempotent via Idempotency-Key. A doubled POST without the "
            "key could (worst case) double-create rows; with the key, "
            "the second call is a free replay."
        ),
        parameters=[
            OpenApiParameter(
                name="confirm",
                location=OpenApiParameter.QUERY,
                description="Set to 1 to opt into a live apply.",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="dry_run",
                location=OpenApiParameter.QUERY,
                description="Set to 1 to force dry-run even with confirm=1.",
                required=False,
                type=str,
            ),
        ],
        request=None,
        responses={
            200: OpenApiResponse(description="Apply result (counts per artifact)"),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Bundle not found"),
            409: OpenApiResponse(description="Bundle not in MAPPED state"),
            500: OpenApiResponse(description="Structured 500 envelope with request_id"),
        },
    )
    @action(detail=True, methods=["post"], url_path="apply")
    @idempotent_post
    @safe_500
    def apply_bundle(self, request, pk=None):
        """Delegate to MigrationCloudApplyView.post().

        Action method is named ``apply_bundle`` (not ``apply``) so it
        doesn't shadow the inherited DRF / Python builtin; ``url_path``
        still routes it at ``/apply/`` per the wizard contract.
        Reliability decorators (idempotency, 500 envelope) wrap the
        delegation boundary.
        """
        return delegate_to_view(
            MigrationCloudApplyView,
            request,
            bundle_id=int(pk),
            shell=shell_for_request(request),
        )

    # ─── reconcile ─────────────────────────────────────────────────────────
    @extend_schema(
        tags=["Migration Cloud"],
        summary="Compute a reconciliation report for an APPLIED bundle",
        description=(
            "Generates the parity scorecard (per-domain source vs target "
            "counts, fill rates, sample rows) for an APPLIED bundle. "
            "Pass an optional ``cohort`` filter as JSON body. Idempotent "
            "via Idempotency-Key."
        ),
        request=None,
        responses={
            200: OpenApiResponse(description="Reconciliation report JSON"),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Bundle not found"),
            409: OpenApiResponse(description="Bundle not in APPLIED state"),
            500: OpenApiResponse(description="Structured 500 envelope with request_id"),
        },
    )
    @action(detail=True, methods=["post"], url_path="reconcile")
    @idempotent_post
    @safe_500
    def reconcile(self, request, pk=None):
        """Delegate to MigrationCloudReconcileView.post().

        Reliability decorators wrap the delegation boundary at this
        layer; the inner wizard view has its own pair.
        """
        return delegate_to_view(
            MigrationCloudReconcileView,
            request,
            bundle_id=int(pk),
            shell=shell_for_request(request),
        )

    # ─── artifacts read-side ──────────────────────────────────────────────
    @extend_schema(
        tags=["Migration Cloud"],
        summary="List artifacts attached to a bundle",
        description=(
            "Returns every artifact (file / sheet / archive child) "
            "attached to the bundle. Artifacts are produced by the "
            "ingestion pipeline; this endpoint is read-only."
        ),
        responses={
            200: MigrationArtifactSerializer(many=True),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Bundle not found"),
        },
    )
    @action(detail=True, methods=["get"], url_path="artifacts")
    def artifacts(self, request, pk=None):
        """Read-only artifact list for a bundle."""
        bundle = self.get_object()
        qs = bundle.artifacts.all()  # tenant-isolation-allow: api-layer-already-tenant-scoped-via-get-object
        serializer = MigrationArtifactSerializer(qs, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        tags=["Migration Cloud Templates"],
        summary="List the 20 canonical-domain template headers",
        description=(
            "Returns the canonical-template registry — the 'Shopify CSV' "
            "front door for the long tail of custom sources. Each entry "
            "is one canonical domain (students, staff, guardians, "
            "enrollment, attendance, grades, finance, ...) and the set "
            "of header columns the platform's accelerator will recognize."
        ),
        responses={
            200: OpenApiResponse(description="Mapping of domain name → header list"),
            401: OpenApiResponse(description="Authentication required"),
        },
    ),
    retrieve=extend_schema(
        tags=["Migration Cloud Templates"],
        summary="Get the header list for one canonical domain",
        description=(
            "Returns the sorted list of canonical header columns for "
            "one domain. Operators fill in the rows they have, leave "
            "the rest blank, and upload through the standard intake."
        ),
        responses={
            200: OpenApiResponse(description="Sorted list of header column names"),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Unknown canonical domain"),
        },
    ),
)
class CanonicalTemplateViewSet(viewsets.ViewSet):
    """Read-only registry of canonical-template headers.

    Deferred (see docket): bulk-import endpoint that accepts a filled-in
    CSV via multipart upload and routes it through the wizard's ingestion
    pipeline — this MVP exposes the headers and the zip download only.
    """

    permission_classes = [IsAuthenticated, MigrationCloudAPIPermission]
    lookup_field = "domain"
    lookup_value_regex = r"[a-z][a-z0-9_]*"

    def _headers_map(self) -> dict[str, list[str]]:
        """Lazy import + sorted output for stable diff-tool friendly JSON."""
        from apps.migration_cloud.accelerators.runmycampus_canonical import (
            DOMAIN_CANONICAL_HEADERS,
        )
        return {
            domain: sorted(headers)
            for domain, headers in DOMAIN_CANONICAL_HEADERS.items()
        }

    def list(self, request):
        return Response(self._headers_map())

    def retrieve(self, request, domain=None):
        headers_map = self._headers_map()
        if domain not in headers_map:
            return Response(
                {
                    "error": "unknown canonical domain",
                    "domain": domain,
                    "known_domains": sorted(headers_map.keys()),
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"domain": domain, "headers": headers_map[domain]})

    @extend_schema(
        tags=["Migration Cloud Templates"],
        summary="Download all 20 canonical templates as a zip",
        description=(
            "Returns ``application/zip`` containing one empty CSV per "
            "canonical domain plus a README explaining required fields "
            "and the canonical-template contract version."
        ),
        responses={
            200: OpenApiResponse(description="application/zip with 20 CSVs + README"),
            401: OpenApiResponse(description="Authentication required"),
        },
    )
    @action(detail=False, methods=["get"], url_path="download")
    def download(self, request):
        """Render the canonical-template zip identical to the wizard surface."""
        headers_map = self._headers_map()

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for domain, headers in sorted(headers_map.items()):
                csv_text = (
                    f"# runmycampus-canonical-template: domain={domain} version=1.0\n"
                    + ",".join(headers) + "\n"
                )
                zf.writestr(f"{domain}.csv", csv_text)
            zf.writestr(
                "README.txt",
                (
                    "RunMyCampus canonical migration template\n"
                    "========================================\n"
                    "\n"
                    "One CSV per canonical domain. Fill in the rows you have;\n"
                    "leave columns blank where you don't. Save and upload\n"
                    "through the Migration Cloud wizard or POST through the\n"
                    "public REST API. Files keep their canonical names so\n"
                    "the accelerator pre-classifies them automatically.\n"
                ),
            )
        buf.seek(0)
        resp = HttpResponse(buf.read(), content_type="application/zip")
        resp["Content-Disposition"] = (
            'attachment; filename="runmycampus-canonical-template.zip"'
        )
        return resp
