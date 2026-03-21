# §0.1.5 wave runbooks (single compendium)

Verification: quarterly review + link tests in `docs/SOT_0155_EVIDENCE_REGISTER.md`.

## support-impersonation-audit
Log support actions; least-privilege; review `SecurityAuditLog` / impersonation flows; trust center links to policy.

## supply-chain
Run `pip install pip-audit && pip-audit -r requirements.txt` (or project requirements); pin versions per COMPATIBILITY.md; SBOM artifact per SECURITY_POLICY.

## wave4-hr-payroll
Payroll: certified partner connectors per country; HR: people app + contracts roadmap; verify `finance` + `people` boundaries.

## wave4-statutory
Report packs + `reports/` + region presets; statutory returns per RegionConfig; verify ReportPack install per tenant.

## year-rollover-mass-reenroll
`accounts/views_rollover.py` + wizard; test: `apps.accounts.tests` rollover where present; guided checklist in Launch Studio.

## wave4-extended-ops
Visitor/facilities/catering: marketplace connector pattern until first-party; verify ServiceIntegration catalog entries.

## wave4-teaching-depth
Curriculum/MTSS/IEP: academics + evals packs; verify feature flags per school.

## wave4-he-research
Degree audit + addons; sponsored programs: HE roadmap in SOT Phase I; effort reporting external until pack.

## wave4-community
Alumni: `BroadcastCampaign`, people graph; TVET placement: admissions + partner fields.

## wave4-uk-statutory
GBR pack + Ofsted presets + ReportPack; verify `tenant_config` REGIONAL_POLICY_PACKS GBR.

## competitor-migration-playbook
Template: export recipe → column map → CSV diff (BR-04) → shadow → cutover; per vendor add row to `docs/MIGRATION_CSV_DIFF_RUNBOOK.md` appendix.

## migration-maas-sku
SKUs: Discovery, Map, Validate, Go-live war room; SLAs in services contract template.

## paper-digital-sku
Phase 0–3 per §0.1.2 C; partner scanning SLA; OCR paths BUEA + receipt docs.

## credential-vc-roadmap
W3C VC / national wallets: integration spec; Digital ID API extension path.

## tenant-export-exit
Full DB export per tenant schema; documented in RUNBOOK_TENANCY + GDPR erasure request path.

## data-retention-legal-hold
Document retention in compliance app; legal hold flag on records; backup runbook linkage.

## pack-config-longevity
Packs versioned; rollback via marketplace; runtime precedence documented.

## n1-n29-wave8-posture
| ID | Verify |
|----|--------|
| N1–N2 | Launch Studio tours + empty states audit (manual Phase H) |
| N3 | skip-link + contrast on role-home (phase_h_audit) |
| N4 | responsive lint `lint_section8_responsive.py` |
| N5 | offline sync delta API + RESILIENT_EDGE |
| N6–N7 | role_home_engine + progressive disclosure registry |
| N8 | command palette smoke URLs |
| N9–N10 | SLO API + PERF_BUDGET / pre_deploy |
| N11–N12 | SLO targets + oneroster throttle + circuit breaker SMS |
| N13–N15 | trust center templates + audit export commands |
| N16 | SOC2: external audit required — roadmap only until attestation |
| N17–N20 | marketplace impact preview + manifest + webhook dead-letter tests |
| N21–N23 | Django i18n + RTL MENA pack + marketing imagery policy |
| N24–N26 | OBSERVABILITY_SLO + migration runbooks + onboarding checklist |
| N27–N28 | AI gateway tests + EWS internal API |
| N29 | signup deep link + Launch checklist timing |
| Foundation | pre_deploy_gate + bounded context lints |
