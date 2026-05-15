"""Canonical Migration Cloud ontology — the platform's source of truth for "what field is this".

Every source-column the universal pipeline encounters is mapped to one
canonical field in this catalog (or quarantined as "unmapped" for operator
review). The catalog is data, not code: it ships as Python so it's
reviewable in PRs and easy to test, but the resolver respects
``RuntimeDefaults`` overrides so tenants can layer custom synonyms on top
without a deploy.

Structure:
    CANONICAL_ONTOLOGY = {
        "<domain>": {
            "<canonical_field>": {
                "description": str,
                "value_type": "string" | "int" | "decimal" | "date" | "datetime" | "bool" | "enum" | "phone" | "email" | "currency",
                "value_examples": list[str],
                "synonyms": {"<lang>": list[str]},
                "sensitivity": "public" | "internal" | "pii" | "sensitive_pii",
                "required_for": list[str],  # which downstream apply paths require this
            },
        },
    }

The 23 domains here mirror the data-domain inventory referenced in the
roadmap (see ``docs/MIGRATION_UNIVERSAL_INTAKE.md``). Coverage per domain
is intentionally "the bedrock fields" — 5 to 15 fields that any credible
migration needs. Anything else lands as a `metadata.DynamicFieldValue` in
the tenant schema (the platform's schema-less custom-field mechanism).
"""

from __future__ import annotations

from .catalog import (
    CANONICAL_ONTOLOGY,
    DOMAINS,
    all_synonyms,
    domain_for_canonical,
    iter_canonical_fields,
    reset_synonym_overlay_cache,
)

__all__ = [
    "CANONICAL_ONTOLOGY",
    "DOMAINS",
    "all_synonyms",
    "domain_for_canonical",
    "iter_canonical_fields",
    "reset_synonym_overlay_cache",
]
