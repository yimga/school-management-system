# Subprocess Usage Ledger

**Purpose:** §10 "Classify subprocess usage" in the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md).

**Status:** DONE — classified; no user-controlled command strings without validation.

---

## 1. Usage by area

| Area | File | Purpose | Risk |
|------|------|---------|------|
| Document conversion | `apps/portal/document_conversion.py` | subprocess.run for converter | Timeout; no shell=True |
| Document generation | `apps/portal/document_generation.py` | subprocess.run, timeout=90 | Fixed command list |
| Receipt OCR | `apps/finance/receipt_verification.py` | tesseract subprocess | Timeout; stderr captured |
| Diagram | `apps/siteconfig/management/commands/generate_models_diagram.py` | graph_models subprocess | Timeout; management only |
| Regional sync | `apps/siteconfig/management/commands/sync_regional_models.py` | ollama pull subprocess | Management only; model_id allowlist |
| Ollama env sync | `apps/platform_runtime/management/commands/sync_ollama_models.py` | ollama pull subprocess | Management + optional Celery beat; argv list, timeout, allowlist |
| Tests | platform_runtime tests, test_theme_studio | run linters / subprocess | Test-only |

---

## 2. Policy

- **No shell=True** with user input.
- **Timeouts** on all subprocess.run calls.
- **Allowlist** binary paths where possible (marksheet_ocr_command pattern).
- **Management commands** only in trusted contexts.

---

## 3. When adding a new subprocess call (NEXT_50 step 39)

When you add or change subprocess usage in `apps/` or `config/`:

1. **Add a row** to the table in §1 (Area, File, Purpose, Risk).
2. **Apply policy** (§2): no `shell=True` with user input; set `timeout=` on `subprocess.run`; prefer fixed command lists or allowlisted binary paths.
3. **Tests:** Test-only subprocess (e.g. running linters) may stay in test files; list under "Tests" in §1 if not file-specific.

This keeps the ledger the single place for subprocess audit and satisfies "ledger updated when adding subprocess calls."

---

## 4. Completion gate (§10)

- [x] Subprocess usage classified.
- [x] When-adding rule documented (update ledger + follow policy; step 39).

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §10.*
