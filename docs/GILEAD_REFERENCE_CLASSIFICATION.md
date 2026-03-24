# Gilead reference classification (Phase 11)

**Policy:** Product-facing surfaces use **RunMyCampus** naming. Historical “Gilead” may remain only where listed below.

| Class | Examples | Action |
|-------|-----------|--------|
| **Archive / root_history** | `docs/archive/root_history/*` | **Docs only** — historical context; no runtime impact. |
| **Migrations (historical)** | `0012_seed_default_gilead_school.py`, `0013_link_default_admin_to_gilead.py`, theme/report seed migrations | **Migration only** — do not rewrite shipped migrations; follow-up data migrations if defaults must change in DB. |
| **Operational docs** | `CURRENT_SETUP_AND_GOOD_TO_GO.md`, old setup guides | **Docs only** — update or mark **DEPRECATED** when misleading. |
| **Lint-scoped runtime** | `apps/*`, `templates/*`, `config/*` (excluding `migrations/`, `tests/`, `management/commands/` per `lint_gilead_residue.py`) | **Must be clean** — `python scripts/lint_gilead_residue.py` = PASS. |
| **Management commands** | `seed_gilead_demo_users` | **Deprecated** — use `seed_demo_tenant_users`; wrapper prints warning. |
| **Tests** | Emails like `*@gileadtech.edu` in test fixtures | **Test-only** — optional neutralization; not lint-gated. |
| **Inventory / audit scripts** | `generate_platform_inventory.py` “gilead” metric | **Tooling** — not user-facing. |

**Single execution source:** `RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` §3.2.5.
