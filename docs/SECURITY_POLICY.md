# Security and dependency policy (non-negotiable, due in full)

## Dependency and vulnerability management

- **Pinning:** Production dependencies MUST be pinned (exact or minimum version with upper bound). No bare `*` in production.
- **SBOM:** Generate Software Bill of Materials (e.g. `pip cyclonedx -o sbom.json` or equivalent) and retain as build artifact where required.
- **Vulnerability scanning:** CI MUST run a dependency/vulnerability check (e.g. `pip-audit`, `safety`, or Dependabot). Build fails or requires explicit waiver with ticket for known high/critical CVEs.
- **Review frequency:** Dependencies are reviewed on each release and on CVE alerts; bumps require review and tests.
- **CVE triage:** High and critical CVEs must be triaged within 48h; apply patch or document accepted risk and mitigation.

## References

- `docs/architecture/open_source_spine.md`
- `docs/execution/SECURITY_PERFORMANCE_NOTES.md`
- `docs/security_baseline.md`
