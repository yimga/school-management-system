"""Migration Cloud public REST API (v3.27 alpha + v3.29 completion).

DRF surface mirroring the wizard so partners and integrations (incl. the
Companion browser extension) can drive migrations programmatically.

Subpackage layout (v3.27 alpha):
    serializers.py    — ModelSerializers for MigrationBundle / Artifact / Run
    viewsets.py       — BundleViewSet + CanonicalTemplateViewSet
                        (every action decorated with @extend_schema)
    helpers.py        — thin shared helpers delegating to wizard views
    auth.py           — MigrationCloudTokenAuthentication
    permissions.py    — MigrationCloudAPIPermission (staff OR tenant)
    urls.py           — DefaultRouter registration

v3.29 completion adds:
    bulk_artifacts.py    — multipart bulk upload action factory
    sse.py               — Server-Sent Events progress mirror action factory
    scoped_tokens.py     — MigrationCloudAPIToken model + auth + viewset
    webhooks.py          — webhook subscription viewset
    webhook_dispatch.py  — outbound webhook signer + Celery task
    docs.py              — public OpenAPI YAML + Redoc HTML views

The wizard views in ``apps/migration_cloud/views.py`` remain untouched;
this subpackage reuses them via composition/delegation only.
"""
