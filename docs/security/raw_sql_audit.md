# Raw SQL usage audit (security mirror)

**Superseded by the canonical inventory:** Use **[docs/raw_sql_audit.md](../raw_sql_audit.md)** (Section 2.4) for the live **six-file** allowlist, table of retained `cursor.execute` calls, and wrap/delegation notes.

**Enforcement (CI):** `python scripts/lint_raw_sql_usage.py` with `scripts/allowlists/raw_sql_allowlist.json`.

**Why this file exists:** Historical security-folder mirror. Do not duplicate allowlist tables here — they drifted from the canonical audit during repository extractions (**`rls_context_repository`**, **`rls_session_repository`**, etc.). Update **`docs/raw_sql_audit.md`** + allowlist JSON when SQL moves.

---

*Authority: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.4.*
