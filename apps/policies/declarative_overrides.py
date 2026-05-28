"""Declarative tenant overrides loader (E8 follow-up).

Operators ship a single config file (JSON, or YAML when PyYAML is available)
and the loader applies the overrides idempotently. Re-running with the same
file is a no-op.

Schema::

    {
      "version": 1,
      "overrides": [
        {
          "school": "example-academy",   # School.slug
          "policy_key": "admissions.numbering_strategy",
          "value": {"strategy": "sequential", "prefix": "EXA"}
        },
        ...
      ]
    }

Use cases:
  - GitOps-style policy-change reviews (config file in repo + PR review)
  - Onboarding a new school via a known-good override pack
  - Quarterly compliance drift cleanup

The loader writes one `policies.TenantPolicyOverride` row per entry. Removed
entries do NOT auto-delete the corresponding row — use `prune=True` for that
(safer default is leave-in-place).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from django.db import transaction

logger = logging.getLogger(__name__)


@dataclass
class ApplyResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    pruned: int = 0
    errors: list[str] | None = None

    def asdict(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "pruned": self.pruned,
            "errors": list(self.errors or []),
        }


def _load_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml  # type: ignore

            return yaml.safe_load(raw)
        except ImportError as exc:
            raise RuntimeError(
                "PyYAML is not installed. Use JSON or `pip install pyyaml`."
            ) from exc
    return json.loads(raw)


def _validate(payload: dict) -> tuple[list[dict], list[str]]:
    """Return (entries, errors). Bad entries are dropped with an error message."""

    errors: list[str] = []
    entries: list[dict] = []
    if not isinstance(payload, dict):
        return [], ["root payload must be a JSON object"]
    if int(payload.get("version") or 0) != 1:
        errors.append("declarative override file must declare version=1")
    for i, e in enumerate(payload.get("overrides") or []):
        if not isinstance(e, dict):
            errors.append(f"entry {i}: must be an object")
            continue
        if not e.get("school"):
            errors.append(f"entry {i}: missing 'school' slug")
            continue
        if not e.get("policy_key"):
            errors.append(f"entry {i}: missing 'policy_key'")
            continue
        if "value" not in e:
            errors.append(f"entry {i}: missing 'value'")
            continue
        entries.append(e)
    return entries, errors


@transaction.atomic
def apply_overrides_dict(payload: dict, *, prune: bool = False) -> ApplyResult:
    """Apply a parsed payload. Idempotent — same input ⇒ no changes after first apply."""

    from apps.policies.models import TenantPolicyOverride
    from apps.schools.models import School

    entries, errors = _validate(payload)
    result = ApplyResult(errors=errors)

    schools_by_slug = {s.slug: s for s in School.objects.filter(
        slug__in={e["school"] for e in entries}
    )}

    seen_keys: set[tuple[int, str]] = set()
    for e in entries:
        school = schools_by_slug.get(e["school"])
        if school is None:
            result.errors.append(f"unknown school slug: {e['school']!r}")
            continue
        key = (school.pk, e["policy_key"])
        seen_keys.add(key)
        existing = TenantPolicyOverride.objects.filter(
            school=school, policy_key=e["policy_key"]
        ).first()
        if existing is None:
            TenantPolicyOverride.objects.create(
                school=school, policy_key=e["policy_key"], value=e["value"], is_active=True
            )
            result.created += 1
        elif existing.value != e["value"] or not existing.is_active:
            existing.value = e["value"]
            existing.is_active = True
            existing.save(update_fields=["value", "is_active", "updated_at"])
            result.updated += 1
        else:
            result.unchanged += 1

    if prune:
        # Remove rows whose (school, policy_key) is not in seen_keys, restricted
        # to schools present in the payload (we don't want to nuke overrides for
        # schools the operator didn't mention).
        prune_school_ids = {s.pk for s in schools_by_slug.values()}
        existing_rows = TenantPolicyOverride.objects.filter(school_id__in=prune_school_ids)
        for row in existing_rows:
            if (row.school_id, row.policy_key) in seen_keys:
                continue
            row.delete()
            result.pruned += 1

    return result


def apply_overrides_file(path: str, *, prune: bool = False) -> ApplyResult:
    """Load a JSON/YAML file and apply its overrides idempotently."""

    payload = _load_file(path)
    return apply_overrides_dict(payload, prune=prune)
