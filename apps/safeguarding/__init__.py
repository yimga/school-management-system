"""Wave R-D (v3.96.0 — 2026-05-26) — DSL safeguarding workflow.

KCSIE 2026-aligned referral kernel. Designated Safeguarding Lead (DSL) is
the gatekeeper for safeguarding concerns; this kernel encodes the FSM,
category registry, and DSL gating so the parent dashboard / teacher
"raise a concern" flow can be wired up against a single source of truth.

Storage: concerns are recorded as JSONL entries under
``School.settings["safeguarding"]["concerns"]`` (FIFO cap 500, sensitive
narratives sanitized at the boundary). The append-only audit trail uses the
existing ``apps.compliance.models_audit.AuditLog`` with
``sensitivity="CRITICAL"`` — no new model, ZERO new migrations.
"""
