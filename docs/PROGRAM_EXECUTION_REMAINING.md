# Program work not closed by a single code drop

**Canonical execution + Wave 8 status:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) **§0.1.5** (all repo-scoped rows **`[x]`** as of 2026-03-23). **External-only OPEN items** — single list: [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md) (**External** table). This file is **not** a second SOT; it explains **why** some real-world milestones stay outside any git-only closure.

| Area | Why it is multi-sprint or external |
|------|-------------------------------------|
| **SOC 2 / N16 attestation** | Auditor engagement + certificate on file — not one PR. |
| **Vendor / certification / ops** | App store releases, Clever/ClassLink native APIs, third-party WCAG cert, 24/7 NOC, prod BI/CWV staffing — [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md). |
| **SiteSettings full DB column split** | Large migration program — external table in backlog. |
| **DoesNotExist sweep** | Ongoing hardening across hundreds of views; §6 ledger. |
| **csrf_exempt** | Governed allowlist: `scripts/allowlists/csrf_exempt_allowlist.json`. |

**Closed in-repo:** Studio rail tile URL audit (`deep_links._PATHS`, `test_studio_rail_resolution.py`). See [STUDIO_RAIL_CONTROL_PLANE_URLS.md](STUDIO_RAIL_CONTROL_PLANE_URLS.md).
