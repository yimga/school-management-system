"""Migration Cloud public REST API alpha (v3.27).

DRF surface mirroring the wizard so partners and integrations (incl. the
Companion browser extension) can drive migrations programmatically.

Subpackage layout:
    serializers.py — ModelSerializers for MigrationBundle / Artifact / Run
    viewsets.py    — BundleViewSet + CanonicalTemplateViewSet (every action
                     decorated with @extend_schema for OpenAPI coverage)
    helpers.py     — thin shared helpers that delegate to existing wizard views
    auth.py        — MigrationCloudTokenAuthentication (scoped-token MVP)
    permissions.py — MigrationCloudAPIPermission (staff OR tenant match)
    urls.py        — DefaultRouter registration

The wizard views in ``apps/migration_cloud/views.py`` remain untouched;
this subpackage reuses them via composition/delegation only.
"""
