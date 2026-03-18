# Mega-file split plan (BR-12)

**Until `CODEX_STRICT=1` passes:** explicit waiver per file.

| File | Approx LOC | Status | Next split |
|------|------------|--------|------------|
| `apps/schools/super_views.py` | Large | **Partial** | New routes → `super_views_beyond_reach.py` (done for BR-04/07/09) |
| Other hits | per `lint_mega_files.py` | Run with `CODEX_STRICT=1` in CI when ready | Extract catalog/migration already split |

**Waiver rule:** Any file over threshold without split must have **row here** + **owner** + **target quarter**.
