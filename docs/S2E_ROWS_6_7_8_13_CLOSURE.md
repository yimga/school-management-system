# §2e Rows 6, 7, 8, 13 — Closure Certificate

**Status:** **DONE AND DUSTED.** No remaining work for these four rows.

**Single reference:** This file + the table in [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) §2e "done and dusted (granular; nothing left)".

---

## Verification (last run)

| Check | Command | Result |
|-------|---------|--------|
| Django | `python manage.py check` | OK (0 issues) |
| Broad except | `python scripts/lint_broad_except.py --allowlist scripts/allowlists/broad_except_allowlist.json --strict` | Pass (baseline respected) |
| Operating discipline | `python scripts/verify_operating_discipline_docs.py` | Pass (exit 0) |
| Phase H | `python scripts/phase_h_audit.py` | Pass (static) |

---

## Row closure (granular)

| Row | Scope | Left to do |
|-----|--------|------------|
| **6** | Shrink broad_except allowlist | **None.** App code at allowlist 0; migrations/tests out of scope. |
| **7** | log_exception_with_context on exception paths | **None.** Core paths covered; list in broad_exception_audit.md §2e row 7. |
| **8** | Control-plane page maturity + §5.1 + §8 | **None.** CONTROL_PLANE §5.1 checklist every row DONE; §8 remainder = content/tokens only. |
| **13** | Operating discipline / decision architecture | **None.** 9 *_DOC refs in role_home_engine.py → existing docs; verify_operating_discipline_docs in CI. |

---

## Where to look for detail

- **Row 6 & 7:** [broad_exception_audit.md](broad_exception_audit.md) — scope, allowlist, structured-logging list.
- **Row 8:** [CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md](CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md) §5.1 — page maturity table (all DONE).
- **Row 13:** [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md) 10.5.1–10.5.8; `apps/dashboard/role_home_engine.py` *_DOC constants; `scripts/verify_operating_discipline_docs.py`.

Re-run the four commands above anytime to confirm nothing has regressed.
