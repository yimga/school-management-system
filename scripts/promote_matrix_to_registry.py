#!/usr/bin/env python3
"""Promote Phase 1 classification-matrix workflows into the registry.

Reads ``docs/generated/platform_workflow_classification_matrix.json`` and
generates ``apps/platform_runtime/workflow_registry_promoted.py`` containing
a ``WORKFLOWS_PROMOTED`` dict that gets merged into
``apps.platform_runtime.workflow_registry.WORKFLOWS`` at module init.

Selection policy:
  * Only weak workflows (not ``strong`` / ``external_blocked``) — the strong
    set is already covered by hand-seeded entries; external-blocked is
    documented elsewhere.
  * Limited to the top N by risk (critical > high > medium > low) so the
    promoted set stays auditable.

Audience mapping (matrix label -> registry constant):
  ``platform_operator``    -> ``operator``
  ``tenant_school_admin``  -> ``tenant-admin``
  ``teacher``              -> ``teacher``
  ``parent``               -> ``parent``
  ``student``              -> ``student``
  ``support_success``      -> ``operator`` (treated as operator surface)
  ``developer_partner``    -> ``operator`` (operator-adjacent for now)

Default tags applied to every promoted entry:
  * ``needs-review`` (operator should hand-verify before relying on the entry)
  * tag inferred from ``current_status`` (e.g. ``missing-how-to`` -> ``missing-setup``)

Re-run after the matrix is updated; this script is idempotent.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "docs/generated/platform_workflow_classification_matrix.json"
OUT_PATH = ROOT / "apps/platform_runtime/workflow_registry_promoted.py"

AUDIENCE_MAP = {
    "platform_operator": "operator",
    "tenant_school_admin": "tenant-admin",
    "teacher": "teacher",
    "parent": "parent",
    "student": "student",
    "support_success": "operator",
    "developer_partner": "operator",
    "founder": "founder",
    "public": "public",
}

STATUS_TO_TAG = {
    "missing_how_to": "missing-setup",
    "missing_info_tags": "needs-review",
    "missing_ai_help": "needs-review",
    "too_many_clicks": "needs-review",
    "fragmented": "needs-review",
    "usable_but_unclear": "needs-review",
}

RISK_TO_TAG = {
    "critical": "blocks-launch",
    "high": "needs-review",
    "medium": "needs-review",
    "low": "optional",
}

# Status that filters OUT of promotion (already handled / not weak)
STRONG_STATUSES = {"strong", "external_blocked"}

RISK_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

TOP_N = 40  # Promote the top 40 weak workflows by risk


def map_audience(matrix_audiences: list[str]) -> str:
    """Pick a single registry audience from the matrix's list."""
    if not matrix_audiences:
        return "operator"
    # Prefer first-listed audience; fall through if unmapped
    for a in matrix_audiences:
        if a in AUDIENCE_MAP:
            return AUDIENCE_MAP[a]
    return "operator"


def slugify_module(matrix_module: str) -> str:
    """Matrix has ``apps/<x>/``; we want ``<x>`` (the registry stores app slug)."""
    if not matrix_module:
        return ""
    parts = matrix_module.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "apps":
        return parts[1]
    return parts[0] if parts else ""


def tags_for_entry(matrix_entry: dict) -> tuple[str, ...]:
    tags: list[str] = ["needs-review"]
    status = matrix_entry.get("current_status", "")
    status_tag = STATUS_TO_TAG.get(status)
    if status_tag and status_tag not in tags:
        tags.append(status_tag)
    risk = matrix_entry.get("risk_level", "")
    risk_tag = RISK_TO_TAG.get(risk)
    if risk_tag and risk_tag not in tags:
        tags.append(risk_tag)
    surface = matrix_entry.get("surface", "")
    if surface == "tenant":
        tags.append("tenant-safe")
    elif surface == "operator":
        tags.append("platform-only")
    return tuple(tags)


AUDIENCE_PREFIX = {
    "operator": "Operator",
    "tenant-admin": "School admin",
    "teacher": "Teacher",
    "parent": "Parent",
    "student": "Student",
    "founder": "Founder",
    "public": "Visitor",
}

# Plain-language replacements applied to purpose text. Deterministic — re-runs
# produce identical output.
COPY_REPLACEMENTS = (
    ("when impact assessment goes south", "when an install needs to be reverted"),
    ("goes south", "needs reverting"),
    ("Subject files", "file an"),
    ("User resolves", "Resolve"),
    ("User selects", "Select"),
    ("User configures", "Configure"),
    # The "AI modelfile" / "AI modelfiles" case: source already has "AI " prefix
    # so we replace the full phrase, not just the suffix, to avoid "AI AI model".
    ("AI modelfiles", "AI model files"),
    ("AI modelfile", "AI model file"),
    ("modelfiles", "AI model files"),
    ("modelfile", "AI model file"),
    # Subject-verb agreement: the original matrix sentence runs in
    # 3rd-person-singular ("Operator configures, publishes, and rolls back").
    # Normalize the whole clause AND insert the colon so the audience-prefix
    # branch sees a fully-formed "Operator: ..." string.
    ("Operator configures, publishes, and rolls back", "Operator: configure, publish, and roll back"),
    ("blueprint", "configuration blueprint"),
    # "and seed Stripe customer" full phrase to avoid "and and link...".
    ("and seed Stripe customer", "and link the billing account"),
    ("seed Stripe customer", "link the billing account"),
    ("structured intake", "a guided form"),
    ("PII migrates", "personal information moves between systems"),
    ("offline edits", "edits saved while offline"),
    ("server state", "the server copy"),
    # Format normalizer: source rows that lead with an audience verb get the
    # canonical "Audience: <imperative>" punctuation. Suppresses the prefix
    # branch (which only fires when text does not already start with the
    # audience word) while restoring the colon for visual consistency.
    # Full-clause forms come first so the trailing 3rd-person verbs flip too.
    (
        "Parent reviews due invoices and either pays via PSP or captures cash receipt",
        "Parent: review due invoices and either pay via PSP or capture a cash receipt",
    ),
    ("Parent reviews", "Parent: review"),
    ("Teacher records", "Teacher: record"),
    ("Teacher enters", "Teacher: enter"),
    ("Operator triages", "Operator: triage"),
)

PURPOSE_MAX_LEN = 240  # cap for the chip / panel text — full goal stays in matrix


def improve_purpose_copy(raw: str, audience: str) -> str:
    """Apply deterministic copy-quality rules to a matrix purpose string.

    Rules:
      * Strip leading "Admin "/"Subject " — replace with audience prefix.
      * Apply ``COPY_REPLACEMENTS`` for known jargon / informal phrasing.
      * Trim trailing whitespace and cap at ``PURPOSE_MAX_LEN``.
      * Prepend an audience-aware lead ("School admin:" etc.) when the
        original sentence does not already name an actor.
    """
    text = (raw or "").strip()
    for src, dst in COPY_REPLACEMENTS:
        text = text.replace(src, dst)
    # Strip generic "Admin" / "User" / "Operator" leads when an audience prefix
    # will be added — avoids "School admin: Admin promotes students..."
    lead_substitutions = (
        ("Admin promotes", "promote"),
        ("Admin imports", "import"),
        ("Admin opens", "open"),
        ("Admin configures", "configure"),
        ("Admin creates", "create"),
        ("Admin approves", "approve"),
        ("Admin generates", "generate"),
        ("Admin requests", "request"),
        ("Admin previews", "preview"),
        ("Admin defines", "define"),
        ("Author defines", "define"),
        ("Tenant admin installs", "install"),
        ("Operator configures", "configure"),
        ("Operator opens", "open"),
        ("User opens", "open"),
        ("User picks", "pick"),
        ("Success rep walks", "walk"),
        ("Pick or upgrade", "pick or upgrade"),
    )
    for src, dst in lead_substitutions:
        if text.startswith(src):
            text = dst + text[len(src):]
            break
    # Add audience prefix when missing and audience is well-known
    prefix = AUDIENCE_PREFIX.get(audience)
    if prefix and not text.lower().startswith(prefix.lower()):
        text = f"{prefix}: {text[0].lower()}{text[1:]}" if text else f"{prefix}: (no description)"
    # Cap length
    if len(text) > PURPOSE_MAX_LEN:
        text = text[: PURPOSE_MAX_LEN - 1].rstrip() + "…"
    return text


def emit_py_repr(value: Any, indent: int = 8) -> str:
    """Emit a Python literal that's safe to paste into a frozen dataclass call."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        # Use double-quoted repr but with escape safety
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        if not value:
            return "()"
        items = ", ".join(emit_py_repr(v, indent + 4) for v in value)
        return f"({items},)" if len(value) == 1 else f"({items})"
    return repr(value)


def render_definition(entry: dict) -> str:
    """Render one WorkflowDefinition(...) call from a matrix entry."""
    key = entry["workflow_id"]
    title = entry.get("workflow_name", key.replace("-", " ").title())
    audience = map_audience(entry.get("audience", []))
    module = slugify_module(entry.get("module", ""))
    route = entry.get("entry_route", "")
    raw_purpose = entry.get("primary_goal", "")
    purpose = improve_purpose_copy(raw_purpose, audience)
    prerequisites = tuple(entry.get("prerequisites", []) or ())
    success_state = entry.get("completion_route_or_state", "")
    tags = tags_for_entry(entry)

    return (
        f'    "{key}": WorkflowDefinition(\n'
        f'        key={emit_py_repr(key)},\n'
        f'        title={emit_py_repr(title)},\n'
        f'        audience={emit_py_repr(audience)},\n'
        f'        module={emit_py_repr(module)},\n'
        f'        route={emit_py_repr(route)},\n'
        f'        purpose={emit_py_repr(purpose)},\n'
        f'        prerequisites={emit_py_repr(prerequisites)},\n'
        f'        success_state={emit_py_repr(success_state)},\n'
        f'        default_tags={emit_py_repr(tags)},\n'
        f'        entry_path={emit_py_repr(route if route.startswith("/") else None)},\n'
        f'        source="matrix-promoted",\n'
        f'    ),\n'
    )


def main() -> int:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    workflows = matrix["workflows"]

    # Filter weak + sort by risk
    weak = [w for w in workflows if w.get("current_status") not in STRONG_STATUSES]
    weak.sort(key=lambda w: (RISK_ORDER.get(w.get("risk_level", "low"), 99), w.get("workflow_id", "")))
    promoted = weak[:TOP_N]

    out = []
    out.append('"""Auto-generated: matrix-promoted workflows merged into the main registry.\n')
    out.append('\nGenerated by ``scripts/promote_matrix_to_registry.py`` from\n')
    out.append('``docs/generated/platform_workflow_classification_matrix.json``.\n')
    out.append('\nDO NOT hand-edit. Re-run the promoter to refresh.\n')
    out.append('"""\n')
    out.append('from __future__ import annotations\n')
    out.append('\n')
    out.append('from apps.platform_runtime.workflow_registry import WorkflowDefinition\n')
    out.append('\n')
    out.append(f'# Generated {datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}.\n')
    out.append(f'# Source: docs/generated/platform_workflow_classification_matrix.json\n')
    out.append(f'# Selected: top {TOP_N} weak workflows by risk.\n')
    out.append('\n')
    out.append('WORKFLOWS_PROMOTED: dict[str, WorkflowDefinition] = {\n')
    for entry in promoted:
        out.append(render_definition(entry))
    out.append('}\n')

    OUT_PATH.write_text("".join(out), encoding="utf-8")
    print(f"Wrote {OUT_PATH.relative_to(ROOT)} with {len(promoted)} promoted workflows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
