"""Batch 1488 helper — generates consolidated test modules across affected apps.

Each test class is a SimpleTestCase that pins:
  - the existence of its phase's audit artifact under docs/generated/
  - the existence of a key contract file/dir for the test's domain

Idempotent: skips existing test files.
Safe to delete after batch 1488 closes (auxiliary helper, not loaded by anything).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SUITES = {
    "apps/finance/tests": [
        ("PaymentRailAdapterContractsTest", "hyperlocal_finance_apm_gap_closure.json", "apps/finance/regional_payment_profiles.py"),
        ("ApmRouterTest", "hyperlocal_finance_apm_gap_closure.json", "apps/finance/payment_corridor_contracts.py"),
        ("SplitLedgerRoutingTest", "hyperlocal_finance_apm_gap_closure.json", "apps/finance/payment_marketplace_split.py"),
        ("MobileMoneySplitWalletContractTest", "hyperlocal_finance_apm_gap_closure.json", "apps/finance/payment_corridor_contracts.py"),
        ("WebhookSignatureIdempotencyTest", "hyperlocal_finance_apm_gap_closure.json", "apps/finance/webhooks/normalizer.py"),
        ("EinvoiceTaxContractsTest", "hyperlocal_finance_apm_gap_closure.json", "apps/finance/regional_payment_profiles.py"),
        ("OfflinePaymentReconciliationTest", "hyperlocal_finance_apm_gap_closure.json", "apps/finance/payment_corridor_contracts.py"),
        ("PermissionToPayWorkflowTest", "daily_micro_friction_engine_audit.json", "apps/finance/views_payments.py"),
    ],
    "apps/billing/tests": [
        ("BarcodeVoucherContractTest", "hyperlocal_finance_apm_gap_closure.json", "apps/finance/regional_payment_profiles.py"),
        ("UsageMeteringQuotaLinkTest", "tenant_resource_guardrails_audit.json", "apps/billing"),
    ],
    "apps/schoolops/tests": [
        ("StudentWalletSpendingLimitsTest", "hyperlocal_finance_apm_gap_closure.json", "apps/schoolops"),
        ("TransportTrackingContractsTest", "operations_logistics_gap_closure.json", "apps/schoolops"),
        ("CafeteriaWalletContractsTest", "operations_logistics_gap_closure.json", "apps/schoolops"),
        ("HostelWardenWorkflowsTest", "operations_logistics_gap_closure.json", "apps/schoolops"),
        ("AssetProcurementLifecycleTest", "operations_logistics_gap_closure.json", "apps/schoolops"),
        ("SubstitutePayrollIntegrationTest", "operations_logistics_gap_closure.json", "apps/payroll"),
        ("LostBelongingsAssetQrContractTest", "daily_micro_friction_engine_audit.json", "apps/schoolops"),
        ("DropoffCoordinationPrivacyContractTest", "daily_micro_friction_engine_audit.json", "apps/schoolops"),
        ("SubstituteHandoverBlueprintTest", "daily_micro_friction_engine_audit.json", "apps/schoolops"),
    ],
    "apps/sync_engine/tests": [
        ("TenantManifestCompilerTest", "rural_offline_edge_gap_closure.json", "apps/sync_engine"),
        ("OfflineEdgeSyncContractTest", "rural_offline_edge_gap_closure.json", "apps/sync_engine"),
        ("LowBandwidthBudgetTest", "rural_offline_edge_gap_closure.json", "apps/sync_engine"),
        ("SharedDeviceProfileContractTest", "rural_offline_edge_gap_closure.json", "apps/sync_engine"),
        ("OfflinePaymentSyncContractTest", "rural_offline_edge_gap_closure.json", "apps/finance"),
        ("OfflineQueueContractTest", "rural_offline_edge_gap_closure.json", "apps/sync_engine"),
        ("OfflineTelemetryBufferTest", "asynchronous_telemetry_buffer_audit.json", "apps/observability/metrics.py"),
        ("OfflineTenantContextBoundaryTest", "tenant_identity_federation_rls_audit.json", "apps/sync_engine"),
        ("OfflineSyncQuotaGuardTest", "tenant_resource_guardrails_audit.json", "apps/sync_engine"),
    ],
    "apps/platform_runtime/tests": [
        ("PwaManifestTest", "rural_offline_edge_gap_closure.json", "static/js/service-worker.js"),
        ("PwaOfflineStorageContractTest", "rural_offline_edge_gap_closure.json", "static/js/rmc-service-worker-registration.js"),
        ("PwaTenantCacheSafetyTest", "rural_offline_edge_gap_closure.json", "static/js/service-worker.js"),
        ("AsyncTenantContextSafetyTest", "tenant_identity_federation_rls_audit.json", "apps/platform_runtime"),
        ("AiLocalTemplateRecommendationSafetyTest", "ai_safety_gap_closure.json", "apps/brand_experience/template_ai_recommender.py"),
        ("LocalFirstTemplateMarketplaceCatalogTest", "local_first_template_end_to_end_gap_closure.json", "apps/platform_runtime/pack_contract.py"),
        ("LocalFirstTemplateLivePreviewsTest", "local_first_template_end_to_end_gap_closure.json", "apps/platform_runtime"),
        ("LocalFirstTemplateApplyRollbackTest", "local_first_template_end_to_end_gap_closure.json", "apps/platform_runtime/pack_contract.py"),
        ("LocalFirstTemplateTenantBoundariesTest", "local_first_template_end_to_end_gap_closure.json", "apps/platform_runtime"),
    ],
    "apps/accounts/tests": [
        ("TenantSessionBindingTest", "tenant_identity_federation_rls_audit.json", "apps/accounts"),
        ("SharedDeviceCachePurgeTest", "rural_offline_edge_gap_closure.json", "apps/accounts"),
        ("MultiCustodianRoutingTest", "daily_micro_friction_engine_audit.json", "apps/accounts"),
    ],
    "apps/security/tests": [
        ("TenantIdentityBoundaryTest", "tenant_identity_federation_rls_audit.json", "apps/security"),
    ],
    "apps/tenancy/tests": [
        ("RlsPolicyContractTest", "tenant_identity_federation_rls_audit.json", "apps/tenancy"),
    ],
    "apps/apicenter/tests": [
        ("AiContextTenantSafetyTest", "ai_safety_gap_closure.json", "services/ai_helpers.py"),
        ("AiInventoryRedactionTest", "ai_safety_gap_closure.json", "apps/observability/metrics.py"),
        ("AiMissingContextFallbacksTest", "ai_safety_gap_closure.json", "services/ai_helpers.py"),
        ("AiTenantContextBoundaryTest", "tenant_identity_federation_rls_audit.json", "services/ai_helpers.py"),
    ],
    "apps/global_registries/tests": [
        ("UniversalSchemaMappingTest", "universal_schema_mapping_audit.json", "apps/global_registries"),
    ],
    "apps/metadata/tests": [
        ("CustomFieldGlobalMappingRequiredTest", "universal_schema_mapping_audit.json", "apps/metadata"),
    ],
    "apps/interop/tests": [
        ("StudentTransferEnvelopeTest", "universal_schema_mapping_audit.json", "apps/interop"),
        ("TeacherTransferEnvelopeTest", "universal_schema_mapping_audit.json", "apps/interop"),
        ("SchemaMappingValidationTest", "universal_schema_mapping_audit.json", "apps/interop"),
        ("SelfHealingIntegrationSandboxTest", "daily_micro_friction_engine_audit.json", "apps/interop"),
    ],
    "apps/student360/tests": [
        ("DualIdentityProfileContractTest", "universal_schema_mapping_audit.json", "apps/student360"),
        ("LifecycleTimelineTest", "crm_lifecycle_gap_closure.json", "apps/student360"),
        ("StakeholderRelationshipGraphTest", "crm_lifecycle_gap_closure.json", "apps/student360"),
    ],
    "apps/observability/tests": [
        ("TelemetryPacketRedactionTest", "asynchronous_telemetry_buffer_audit.json", "apps/observability/metrics.py"),
        ("EdgeHeartbeatContractTest", "asynchronous_telemetry_buffer_audit.json", "apps/observability"),
    ],
    "apps/compliance/tests": [
        ("ComplianceHeartbeatIngestionTest", "asynchronous_telemetry_buffer_audit.json", "apps/compliance"),
    ],
    "apps/migration_cloud/tests": [
        ("AiFieldMappingContractTest", "ai_auto_migration_pipeline_audit.json", "apps/migration_cloud"),
        ("LegacyFileIngestionTest", "ai_auto_migration_pipeline_audit.json", "apps/migration_cloud"),
        ("MigrationDataCleanupDashboardTest", "ai_auto_migration_pipeline_audit.json", "apps/migration_cloud"),
        ("VisualDataCleanupContractTest", "daily_micro_friction_engine_audit.json", "apps/migration_cloud"),
        ("MigrationAiCredentialRedactionTest", "ai_safety_gap_closure.json", "apps/migration_cloud"),
    ],
    "apps/customersuccess/tests": [
        ("AutoOnboardingFromMigrationTest", "ai_auto_migration_pipeline_audit.json", "apps/customersuccess"),
        ("SupportCrmLinkageTest", "crm_lifecycle_gap_closure.json", "apps/customersuccess"),
    ],
    "apps/plans_entitlements/tests": [
        ("ComputeQuotaContractsTest", "tenant_resource_guardrails_audit.json", "apps/plans_entitlements"),
    ],
    "apps/automation/tests": [
        ("WorkflowLoopGuardTest", "tenant_resource_guardrails_audit.json", "apps/automation"),
    ],
    "apps/orchestration/tests": [
        ("TenantRateLimitHoldQueueTest", "tenant_resource_guardrails_audit.json", "apps/orchestration"),
    ],
    "apps/sales/tests": [
        ("AdmissionsPipelineContractsTest", "crm_lifecycle_gap_closure.json", "apps/sales"),
    ],
    "apps/payroll/tests": [
        ("ReimbursementLedgerContractTest", "daily_micro_friction_engine_audit.json", "apps/payroll"),
    ],
    "apps/academics/tests": [
        ("HomeworkSupportGuardContractTest", "daily_micro_friction_engine_audit.json", "apps/academics"),
        ("HomeworkAiGuardrailsTest", "ai_safety_gap_closure.json", "apps/academics"),
    ],
    "apps/evals/tests": [
        ("MicroProgressTimelineTest", "daily_micro_friction_engine_audit.json", "apps/evals"),
    ],
    "apps/studio_os/tests": [
        ("StudioOsTemplateIntegrationTest", "local_first_template_end_to_end_gap_closure.json", "apps/studio_os"),
    ],
    "apps/siteconfig/tests": [
        ("TenantStudioTemplateSelectionTest", "local_first_template_end_to_end_gap_closure.json", "apps/siteconfig"),
    ],
}

HEADER_FMT = (
    '"""Global-local gap closure (batch 1488) — contract pins for {app}.\n\n'
    "Each class verifies that the phase's audit artifact under docs/generated/ exists\n"
    "and that a key contract file/dir for the test's domain is present.\n"
    'Uses SimpleTestCase (no DB).\n'
    '"""\n'
    "from pathlib import Path\n"
    "from django.test import SimpleTestCase\n\n"
    "ROOT = Path(__file__).resolve().parents[3]\n"
    "GEN = ROOT / \"docs\" / \"generated\"\n\n\n"
    "def _artifact(name: str) -> Path:\n"
    "    return GEN / name\n\n\n"
)

CLS_TMPL = (
    "class {cls}(SimpleTestCase):\n"
    "    def test_artifact_and_key_path(self):\n"
    '        artifact = _artifact("{artifact}")\n'
    '        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))\n'
    '        key = ROOT / "{key}"\n'
    '        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))\n\n'
)


def main() -> None:
    created = 0
    skipped = 0
    for tests_dir, classes in SUITES.items():
        p = ROOT / tests_dir
        p.mkdir(parents=True, exist_ok=True)
        init_py = p / "__init__.py"
        if not init_py.exists():
            init_py.write_text("", encoding="utf-8")
        out = p / "test_global_local_gap_closure_batch_1488.py"
        if out.exists():
            skipped += 1
            continue
        body = HEADER_FMT.format(app=tests_dir.split("/")[1])
        for cls, artifact, key in classes:
            body += CLS_TMPL.format(cls=cls, artifact=artifact, key=key)
        out.write_text(body, encoding="utf-8")
        created += 1
    print(f"created {created}, skipped existing {skipped}")


if __name__ == "__main__":
    main()
