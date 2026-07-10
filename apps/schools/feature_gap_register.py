"""
Feature Gap Register — SOT for "what we say we ship" vs "what's actually
demonstrably wired up." Closes the section N item "end_to_end_feature_gap_register"
that previously had no spec to compare against.

The register is the spec. Each row pins a named feature to a status
(`shipped` | `in_progress` | `planned`) and, when shipped, names the
proof: a route, a model class, a management command, or a CI gate. A
regression test asserts every `shipped` row's proof actually resolves.

Add a row HERE before claiming a feature in marketing. Removing a row
removes the public promise — never do that silently.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class FeatureRow:
    """One platform feature with status + proof location."""

    feature_slug: str
    """Stable kebab-case key. Stored in dashboards; never renamed."""

    label: str
    """Human-readable feature name."""

    capability_domain: str
    """Coarse grouping: identity / billing / classroom / reporting / governance / integrations / studio_os / observability / ai."""

    status: str = "shipped"
    """`shipped` | `in_progress` | `planned`."""

    proof_route_name: str | None = None
    """Django URL name that demonstrates the feature is wired up."""

    proof_model: str | None = None
    """`app_label.ModelName` of the canonical model backing the feature."""

    proof_management_command: str | None = None
    """Name of a `python manage.py <cmd>` that exercises the feature."""

    proof_ci_gate: str | None = None
    """Name of the architectural CI gate (scanner) that enforces the feature."""

    public_promise: bool = False
    """True if marketing surfaces this feature. Drives drift assertions."""

    notes: str = ""

    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FEATURE_REGISTER: tuple[FeatureRow, ...] = (
    FeatureRow(
        feature_slug="ai-center",
        label="AI Center (unified governed assistants)",
        capability_domain="ai",
        proof_route_name="siteconfig:ai_center",
        public_promise=True,
        notes="One canonical surface for every governed AI assistant. Replaces per-page broken cards.",
    ),
    FeatureRow(
        feature_slug="ai-governance",
        label="AI governance dashboard",
        capability_domain="ai",
        proof_route_name="siteconfig:ai_governance",
        public_promise=True,
    ),
    FeatureRow(
        feature_slug="role-permission-matrix",
        label="Role / permission matrix scanner + CI gate",
        capability_domain="governance",
        proof_ci_gate="audit_role_permission_matrix",
        notes="v2.83 ratchet at --max-candidate-anonymous 66. Per-file alias resolution + auth-mixin propagation.",
    ),
    FeatureRow(
        feature_slug="public-to-product-promise-matrix",
        label="Public-to-Product Promise Matrix",
        capability_domain="governance",
        proof_route_name="manager_public_to_product_matrix",
        public_promise=True,
        notes="Manager-host surface; data SOT in apps/schools/public_product_promise_matrix.py.",
    ),
    FeatureRow(
        feature_slug="feature-gap-register",
        label="Feature gap register (this surface)",
        capability_domain="governance",
        proof_route_name="manager_feature_gap_register",
        public_promise=False,
    ),
    FeatureRow(
        feature_slug="data-quality-center",
        label="Data Quality Center",
        capability_domain="governance",
        proof_route_name="compliance:data_quality_center",
        public_promise=True,
    ),
    FeatureRow(
        feature_slug="api-center",
        label="API Center (integrations + keys + webhooks)",
        capability_domain="integrations",
        proof_route_name="apicenter:dashboard",
        public_promise=True,
    ),
    FeatureRow(
        feature_slug="integrations-marketplace",
        label="Integrations Marketplace (Zoom/Meet/Teams/Outlook/Gmail/Slack)",
        capability_domain="integrations",
        proof_route_name="integrations_marketplace:hub",
        public_promise=True,
    ),
    FeatureRow(
        feature_slug="studio-os-shell",
        label="Studio OS shell",
        capability_domain="studio_os",
        proof_route_name="studio_os:shell",
        public_promise=True,
    ),
    FeatureRow(
        feature_slug="studio-os-control",
        label="Studio OS — Control mode",
        capability_domain="studio_os",
        proof_route_name="studio_os:control",
    ),
    FeatureRow(
        feature_slug="studio-os-experience",
        label="Studio OS — Experience mode",
        capability_domain="studio_os",
        proof_route_name="studio_os:experience",
    ),
    FeatureRow(
        feature_slug="studio-os-automation",
        label="Studio OS — Automation mode",
        capability_domain="studio_os",
        proof_route_name="studio_os:automation",
    ),
    FeatureRow(
        feature_slug="studio-os-output",
        label="Studio OS — Output mode",
        capability_domain="studio_os",
        proof_route_name="studio_os:output",
    ),
    FeatureRow(
        feature_slug="studio-os-launch",
        label="Studio OS — Launch mode",
        capability_domain="studio_os",
        proof_route_name="studio_os:launch",
    ),
    FeatureRow(
        feature_slug="help-center",
        label="Help Center landing",
        capability_domain="governance",
        proof_route_name="feedback:help_center",
        public_promise=True,
    ),
    FeatureRow(
        feature_slug="release-notes",
        label="Public release notes feed",
        capability_domain="governance",
        proof_route_name="feedback:release_notes_public",
        public_promise=True,
    ),
    FeatureRow(
        feature_slug="notification-preferences",
        label="User notification preferences (per-channel)",
        capability_domain="identity",
        proof_route_name="accounts:notification_preferences",
        notes="v2.84. Channels: email / sms / push / in_app + weekly_summary toggle.",
    ),
    FeatureRow(
        feature_slug="first-school-readiness-preflight",
        label="First-school readiness preflight",
        capability_domain="governance",
        proof_management_command="verify_platform_readiness",
        notes="6 criteria per tenant: academic_year, term, classroom, active_teacher, active_student, brand_name.",
    ),
    FeatureRow(
        feature_slug="first-school-operating-proof",
        label="First-school operating proof (Playwright)",
        capability_domain="governance",
        proof_ci_gate="first-school-operating-proof.yml",
        notes="8-stage lifecycle; needs 3 staging secrets to activate.",
    ),
    FeatureRow(
        feature_slug="render-parity-probe",
        label="Render-parity probe (deployed vs local routes)",
        capability_domain="observability",
        proof_ci_gate="render-parity.yml",
    ),
    FeatureRow(
        feature_slug="api-center-browser-proof",
        label="API Center browser proof (Playwright)",
        capability_domain="integrations",
        proof_ci_gate="first-school-operating-proof.yml",
        notes="API Center spec lives alongside the first-school proof workflow.",
    ),
    FeatureRow(
        feature_slug="tenant-isolation-scanner",
        label="Tenant isolation scanner (RLS-style enforcement)",
        capability_domain="governance",
        proof_ci_gate="scan_tenant_queryset_safety",
        notes="Baseline 730. Annotate cross-tenant queries with `# tenant-isolation-allow:`.",
    ),
    FeatureRow(
        feature_slug="bank-account-dual-auth",
        label="Bank account four-eyes dual auth",
        capability_domain="billing",
        proof_model="finance.BankAccountChangeRequest",
        notes="v2.60. State machine PENDING→APPROVED/REJECTED/EXPIRED.",
    ),
    FeatureRow(
        feature_slug="impersonation-dual-control",
        label="School impersonation dual-control",
        capability_domain="identity",
        proof_model="schools.School",
        notes="Pattern shared with BankAccount dual-auth (v2.60).",
    ),
    FeatureRow(
        feature_slug="csp-enforce-mode",
        label="CSP enforce mode (style-src self only)",
        capability_domain="governance",
        proof_ci_gate="scan_inline_style_off_token",
        notes="v2.60 flip. Zero-tolerance gate; baseline 0.",
    ),
    FeatureRow(
        feature_slug="emotional-ux-confidence",
        label="Emotional UX confidence audit",
        capability_domain="governance",
        status="shipped",
        proof_route_name="feedback:voice_of_customer",
        proof_model="feedback.SurveyResponse",
        notes="SHIPPED 2026-06-09: CSAT/NPS/CES/workflow pulse responses and contextual feedback aggregate in Voice of Customer. The platform records evidence; it does not fabricate a positive result without respondents.",
    ),
    FeatureRow(
        feature_slug="feedback-loop-live-usage",
        label="Feedback loop live usage telemetry",
        capability_domain="governance",
        status="shipped",
        proof_route_name="feedback:contextual",
        proof_model="feedback.FeedbackSubmission",
        notes="SHIPPED 2026-06-09: every Was this helpful control posts a tenant-scoped contextual FeedbackSubmission; Voice of Customer consumes real rows by school, role, module, sentiment, and pain point.",
    ),
    # --- Glocal local-first lifecycle (docs/GLOCAL_SOVEREIGNTY_PLAN.md, 2026-06-07) ---
    # Lifecycle rows from the "Cloud-Dependency-Collapse" manifest.
    # A shipped row must retain a resolving proof_* and an honest scope note.
    FeatureRow(
        feature_slug="offline-intake-wizard",
        label="Offline-first intake wizard (IndexedDB-cached registration)",
        capability_domain="identity",
        status="shipped",
        proof_route_name="setup_studio:tenant_wizard_index",
        notes="SHIPPED 2026-06-09: enable_offline_intake_wizard gates AES-GCM-wrapped Dexie/IndexedDB step drafts with explicit restore/discard and no automatic authoritative write.",
    ),
    FeatureRow(
        feature_slug="data-residency-routing",
        label="Sovereign data router (PII residency by signup country)",
        capability_domain="governance",
        status="shipped",
        proof_management_command="verify_data_residency",
        proof_model="schools.School",
        notes="SHIPPED Wave A 2026-06-07: School.data_region (regulatory) + regional_cluster (operational) + verify_data_residency command (--strict/--fix-derive), on top of app.current_school_id RLS.",
    ),
    FeatureRow(
        feature_slug="vocabulary-injector",
        label="Cultural vocabulary injector (server-side role/term localization)",
        capability_domain="identity",
        status="shipped",
        proof_management_command="verify_terminology_cascade",
        notes="SHIPPED Wave A 2026-06-07: 6-layer terminology cascade (siteconfig/terminology_service.py resolve_term: classroom→school→ancestors→curriculum→country overlay→registry) + context_processor emits to all templates. Verifier verify_terminology_cascade.",
    ),
    FeatureRow(
        feature_slug="timetable-solver",
        label="Offline conflict-free timetable / resource solver",
        capability_domain="studio_os",
        status="shipped",
        proof_route_name="academics:timetable_generate",
        notes="SHIPPED and repaired 2026-06-09: bounded backtracking expands weekly occurrences and enforces locked slots, teacher/room availability, room kind, and class/teacher/room collisions, with tested greedy fallbacks. 2026-07-10: the in-product surface converged onto the persisting Stack-A flow (generate -> review clashes -> publish); the JSON-console dead-end was retired.",
    ),
    FeatureRow(
        feature_slug="dual-identity-profile",
        label="Dual-identity profile matrix (day school + evening coaching)",
        capability_domain="identity",
        status="shipped",
        proof_model="academics.StudentDegreeEnrollment",
        notes="SHIPPED 2026-06-09: Student 360 projects one StudentProfile into its primary classroom/year identity plus active program enrollments, including schedule_mode and meeting_windows.",
    ),
    FeatureRow(
        feature_slug="substitute-broker",
        label="1-click substitute broker (absence → WhatsApp/SMS broadcast)",
        capability_domain="classroom",
        status="shipped",
        proof_route_name="accounts:ops_substitutes",
        proof_model="schoolops.SubstituteCover",
        notes="SHIPPED 2026-06-09: tenant-scoped discovery excludes absent/already-booked staff, ranks department/priority/load deterministically, and broadcasts through consent-aware WhatsApp with durable SMS fallback. Redacted time-boxed handover packets remain the access boundary.",
    ),
    FeatureRow(
        feature_slug="split-wallet-checkout",
        label="Split-wallet checkout (multi-payer / multi-line allocation)",
        capability_domain="billing",
        status="shipped",
        proof_route_name="finance:split_allocation",
        proof_model="finance.InvoicePayerShare",
        notes="SHIPPED Wave A 2026-06-07: finance:split_allocation view builds an Invoice with per-fee InvoiceLines + InvoicePayerShare rows (equal or custom %), Decimal-safe, transaction.atomic, posts to ledger. Tests: test_split_allocation/test_split_billing.",
    ),
    FeatureRow(
        feature_slug="cashless-campus-pos",
        label="Cashless campus POS (QR / RFID / biometric → wallet debit)",
        capability_domain="billing",
        status="shipped",
        proof_route_name="api:pos-checkout",
        proof_model="schoolops.PosSaleLine",
        notes="SHIPPED Wave C 2026-06-07: POST /api/pos/checkout/ (PosCheckoutAPI) → schoolops/pos_checkout.checkout: resolve student by id or scanned credential (student_code), debit schoolops.MealPlanBalance atomically (Decimal-safe, select_for_update), record student-linked PosSaleLine (migration 0024 added student FK + idempotency_key). Idempotent per key. Tests test_pos_checkout 8/8. (Multi-terminal offline debit reservation deferred to Wave F mesh.)",
    ),
    FeatureRow(
        feature_slug="allergen-barrier-pos",
        label="Allergen barrier (health → cafeteria sale-block at the terminal)",
        capability_domain="classroom",
        status="shipped",
        proof_route_name="api:pos-checkout",
        proof_model="schoolops.HealthRecord",
        notes="SHIPPED Wave C 2026-06-07: pos_checkout.allergen_conflict cross-refs schoolops.HealthRecord allergy rows + Allergy tags against the item label; checkout() refuses the sale (409) before any debit when a term matches. Honours the POS wizard allergen_dietary_rules setting (safety-first default ON). Tests cover block + disable. NOTE: keyword match, not NLP.",
    ),
    FeatureRow(
        feature_slug="fiscal-einvoice-adapters",
        label="Fiscal e-invoice adapters (SAT/SEFAZ stamped invoices)",
        capability_domain="billing",
        status="shipped",
        proof_management_command="verify_fiscal_einvoice_adapters",
        notes="SHIPPED repository scope 2026-06-09: deterministic CFDI 4.0 unsigned XML and NF-e 4.00 provider-envelope adapters, total validation, stable idempotency, pluggable signing/transport, and fail-closed behavior without certificates/provider credentials. Authority stamping remains operator configuration.",
    ),
    FeatureRow(
        feature_slug="bluetooth-proximity-attendance",
        label="Proximity attendance ingest (device-agnostic: BLE/RFID/NFC/QR)",
        capability_domain="classroom",
        status="shipped",
        proof_route_name="api:proximity-attendance-ingest",
        proof_model="academics.Attendance",
        notes="SHIPPED Wave B 2026-06-07: POST /api/proximity/attendance/ingest/ (ProximityAttendanceIngestAPI) → academics/proximity_attendance.record_proximity_checkin queues an offline ATTENDANCE action (idempotent per device+student+date) that drains into academics.Attendance with a proximity audit remark. Flag enable_offline_proximity_attendance_sync. Tests test_proximity_attendance 6/6. Device side (radio) is external by design.",
    ),
    FeatureRow(
        feature_slug="omr-scan-grading",
        label="OCR marksheet proposal and teacher-confirmed grade sync",
        capability_domain="classroom",
        status="shipped",
        proof_route_name="evals:teacher_marks_entry",
        proof_model="evals.Evaluation",
        notes="SHIPPED and hardened 2026-06-08: server Tesseract and self-hosted Tesseract.js create proposals only. Browser proposals preserve confidence/source coordinates and fill review-highlighted gradebook cells; server proposals require checked teacher attestation. Accepted browser proposals use the existing grade WAL/outbox and manual conflict policy. No confidence threshold can auto-write an Evaluation. Plickers card-sweep remains a distinct CV capability.",
    ),
    FeatureRow(
        feature_slug="plickers-card-sweep",
        label="Plickers-style card-sweep grading (no-device, camera shape-parse)",
        capability_domain="classroom",
        status="shipped",
        proof_route_name="evals:teacher_marks_entry",
        proof_model="evals.Evaluation",
        notes="SHIPPED 2026-06-09: browser BarcodeDetector scans QR student cards, infers A/B/C/D from card corner rotation, and creates highlighted 20/0 exam proposals against the selected answer. It never fetches, submits, or writes Evaluation rows; teacher review and the existing save/WAL remain mandatory.",
    ),
    FeatureRow(
        feature_slug="zero-data-homework-buffer",
        label="Zero-data homework queue buffer (<500KB cache, gate sync)",
        capability_domain="classroom",
        status="shipped",
        proof_management_command="",
        proof_model="platform_runtime.OfflineAction",
        notes="SHIPPED 2026-06-08 (zero-friction Phase 2a): OfflineAction.ActionType.HOMEWORK_SUBMISSION + _apply_homework_submission in offline_queue.py (submit_student_work → store_submission in School.settings academics bucket); enable_offline_homework_sync in offline_mode_bundle + platform_surface_config homeworkSyncEnabled; SODP homework.submit validation. Tests: test_offline_queue homework submission path.",
    ),
    FeatureRow(
        feature_slug="smart-fleet-route-optimizer",
        label="Offline greedy bus-route optimizer (nearest-neighbour)",
        capability_domain="logistics",
        status="shipped",
        proof_management_command="optimize_bus_route",
        proof_model="schoolops.Stop",
        notes="SHIPPED 2026-06-07 (prerequisite closed): added Stop.latitude/longitude (migration 0026); schoolops/route_optimizer.py haversine_km + nearest-neighbour optimize_stop_order/optimize_route (offline, no map API, two-phase sequence persist respecting the unique constraint) + optimize_bus_route command. Tests test_route_optimizer 7/7. Honest scope: greedy kernel; true VRP/2-opt is a later pass.",
    ),
    FeatureRow(
        feature_slug="rfid-fleet-monitor",
        label="Non-phone RFID/NFC/QR boarding monitor → parent feed",
        capability_domain="logistics",
        status="shipped",
        proof_route_name="api:bus-boarding-ingest",
        proof_model="schoolops.BusBoardingEvent",
        notes="SHIPPED Wave D 2026-06-07: POST /api/transport/boarding/ingest/ (BusBoardingIngestAPI) → schoolops/boarding_monitor.record_boarding writes append-only BusBoardingEvent (migration 0025), resolves route from TransportAssignment, idempotent per tap, best-effort guardian notify (parent_notified flag). Tests test_boarding_monitor 5/5.",
    ),
    FeatureRow(
        feature_slug="field-trip-compliance",
        label="Field-trip compliance (e-sign consent + offline medical checklist)",
        capability_domain="governance",
        status="shipped",
        proof_model="compliance.ConsentRequest",
        notes="SHIPPED 2026-06-07: schoolops/field_trip.py create_field_trip_consent (reuses ConsentRequest category=field_trip + SHA-256 ConsentRecord e-sign) + build_medical_checklist (confidential, offline-carryable, NOT masked — real name/allergies/meds/emergency contact from HealthRecord for supervising-teacher safety). Tests test_field_trip 3/3.",
    ),
    FeatureRow(
        feature_slug="auditor-magic-link",
        label="One-click auditor gateway (time-bounded, PII-masked, access-logged)",
        capability_domain="governance",
        status="shipped",
        proof_route_name="compliance:auditor_inspect",
        proof_model="compliance.AuditorAccessGrant",
        notes="SHIPPED Wave E 2026-06-07: operator mints a revocable time-bounded grant (compliance.AuditorAccessGrant, migration 0016) → TimestampSigner magic link; PUBLIC token-gated inspector view (compliance:auditor_inspect) needs no login (the signed unexpired unrevoked grant IS the auth), returns ONLY pii_masking.mask_student_for_auditor projections (initials, birth-year, guardian withheld), and logs every view to AuditorAccessLog. Operator console create/list/revoke (staff-gated). Geo-fence ENFORCED 2026-06-07 (migration 0018): AuditorAccessGrant.ip_allowlist + auditor_access.ip_is_allowed (stdlib ipaddress, CIDR-aware, fail-closed when a geo-fenced grant's client IP is unplaceable); auditor_inspect returns 403 off-net and records the denial (AuditorAccessLog.allowed/denied_reason); empty allowlist = no restriction (opt-in). Tests test_auditor_access 12/12 (+2 command).",
    ),
    FeatureRow(
        feature_slug="non-repudiation-logger",
        label="Platform-wide signed, append-only non-repudiation action log",
        capability_domain="observability",
        status="shipped",
        proof_model="compliance.NonRepudiationLogEntry",
        proof_management_command="verify_non_repudiation_chain",
        notes="SHIPPED 2026-06-07: compliance.NonRepudiationLogEntry (migration 0017, per-school SHA-256 hash chain + HMAC server signature, append-only save/delete guards) + non_repudiation.record_action/verify_chain (any app records actions; tamper to payload OR signature is detected) + verify_non_repudiation_chain command. Tests test_non_repudiation 7/7. WebAuthn user-presence is the client layer — bound per-entry via webauthn_presence when supplied; write-once S3 Object Lock vault is a deploy-side mirror, future.",
    ),
    FeatureRow(
        feature_slug="gdpr-key-shredding",
        label="GDPR Right-to-be-Forgotten erasure (anonymization, SLA-tracked)",
        capability_domain="governance",
        status="shipped",
        proof_model="compliance.EraseRequest",
        proof_management_command="process_erase_requests",
        notes="SHIPPED Wave A 2026-06-07 as ANONYMIZATION (Art.17): EraseRequest (PENDING→APPROVED→COMPLETED, SLA fields) + gdpr_services.fulfill_pending_erasure → gdpr_scrub_student + process_erase_requests command + URLs (erasure_request/data_portability_export). HONEST GAP: literal crypto key-shred preserving aggregates is a future upgrade (slug kept for continuity; label corrected to what ships).",
    ),
    FeatureRow(
        feature_slug="state-reporting-bridges",
        label="State-reporting CSV exporter (per-jurisdiction column maps)",
        capability_domain="reporting",
        status="shipped",
        proof_management_command="export_state_report",
        notes="SHIPPED 2026-06-07: apps/reports/state_reporting.py JURISDICTION_FORMATS (GENERIC / US_EDFACTS / CA_CALPADS column maps) + export_state_report_csv (offline CSV packet) + export_state_report command, on the statutory_tenant_extract + interop/ceds+edfi foundation. Tests test_state_reporting 5/5. Honest scope: real column maps + CSV; authority validation rules + transport layer on top.",
    ),
    FeatureRow(
        feature_slug="crdt-offline-convergence",
        label="CRDT offline convergence (LWW-register + G-set + multi-terminal wallet)",
        capability_domain="integrations",
        status="shipped",
        proof_management_command="verify_crdt_convergence",
        notes="SHIPPED Wave F 2026-06-07: apps/sync_engine/crdt.py (LWWRegister ordered by Lamport-clock+replica-id — deterministic, NOT wall-clock LWW; GSet union; lamport_tick) + crdt_wallet.py (grow-only unique-op log, union-merge, Decimal-safe effective_balance, multi-terminal offline debit with HONEST overdraft DETECTION on reconciliation — overdraft is uncoordinatable offline per CAP, so detected not faked; online mode reserve_debit can reject). Proven convergent: tests test_crdt 13/13 + verify_crdt_convergence command. Device-to-device mesh TRANSPORT (BLE/Wi-Fi-Direct) rides on top; rmc-lan-mule-sync.js is the LAN transport. This is the correct home for Wave C's deferred multi-terminal wallet reservation.",
    ),
)


def iter_features() -> tuple[FeatureRow, ...]:
    return FEATURE_REGISTER


def feature_slugs() -> frozenset[str]:
    return frozenset(f.feature_slug for f in FEATURE_REGISTER)


def get_feature(slug: str) -> FeatureRow | None:
    for f in FEATURE_REGISTER:
        if f.feature_slug == slug:
            return f
    return None


def features_by_domain() -> dict[str, list[FeatureRow]]:
    out: dict[str, list[FeatureRow]] = {}
    for f in FEATURE_REGISTER:
        out.setdefault(f.capability_domain, []).append(f)
    return out
