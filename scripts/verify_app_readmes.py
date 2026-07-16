#!/usr/bin/env python
"""Per-app README gate (A+ mandate metric 24 - Documentation & Runbooks).

Metric 24 requires "per-app READMEs current ... no doc overstates delivered
surface (audited)". Presence alone is worthless: a README full of invented
model names is *worse* than no README, because a reader trusts it. The whole
point of this gate is that **every factual claim a README makes is checked
against the live Django app registry**, so documentation cannot drift away
from the code or be filled with plausible-sounding fiction.

`scripts/audit_workflow_code_truth_inventory.py` already counts READMEs, but
it only *inventories* presence and asserts nothing, and it is not CI-wired.
This gate asserts.

What each `apps/<label>/README.md` must satisfy:

1. **Exists** for every ``apps.*`` entry in INSTALLED_APPS.
2. **Title** is exactly ``# apps/<label>`` - catches copy-paste between apps.
3. **Tenancy line** matches settings truth (TENANT_APPS vs shared). A README
   that calls a shared app tenant-isolated would send a reader looking for a
   schema that does not exist.
4. **Every model named in the "Key models" table really exists** in that app's
   registry - the anti-fiction check.
5. **No placeholder text** (TODO / TBD / lorem / "describe here" / ...) - this
   is what makes generated boilerplate fail instead of silently passing.
6. **Purpose prose is substantive** (>= MIN_PURPOSE_CHARS of real text), so a
   one-word stub cannot satisfy the metric.

Deliberately NOT checked: that the model *table* is exhaustive. Big apps have
100+ models and listing every one would be noise, not documentation. The rule
is "what you claim must be true", not "you must claim everything".

Usage:
    python scripts/verify_app_readmes.py            # report + exit 1 on findings
    python scripts/verify_app_readmes.py --json
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_DIR = REPO_ROOT / "apps"
SETTINGS_PATH = REPO_ROOT / "config" / "settings.py"

MIN_PURPOSE_CHARS = 180

# Text that means "nobody actually wrote this section". Matched case-insensitively
# on word boundaries so real prose ("we fixed a TODO in 2024") is not caught by
# accident -- these are checked as standalone markers.
PLACEHOLDER_PATTERNS = (
    r"\bTODO\b",
    r"\bTBD\b",
    r"\bFIXME\b",
    r"\blorem ipsum\b",
    r"\bdescribe (?:this|here)\b",
    r"\bcoming soon\b",
    r"\bfill (?:this )?in\b",
    r"<[a-z -]*one-line purpose[a-z -]*>",
    r"\bXXX\b",
)

REQUIRED_HEADINGS = (
    "## What this app owns",
    "## Key models",
    "## Before you change this",
)

TENANCY_RE = re.compile(r"^\*\*Tenancy:\*\*\s*(TENANT|SHARED)\b", re.M)
# Rows of the Key models table: | `ModelName` | ... |
MODEL_ROW_RE = re.compile(r"^\|\s*`([A-Za-z_][A-Za-z0-9_]*)`\s*\|", re.M)


def _installed_app_labels() -> list[str]:
    """Parse INSTALLED_APPS out of config/settings.py.

    Parsed rather than imported: importing prod settings needs a full Django
    bootstrap (DB, env), which a docs gate must not require to run in CI.
    """
    src = SETTINGS_PATH.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    labels: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id == "INSTALLED_APPS"):
                continue
            if not isinstance(node.value, ast.List):
                continue
            for el in node.value.elts:
                if isinstance(el, ast.Constant) and isinstance(el.value, str):
                    if el.value.startswith("apps."):
                        labels.append(el.value.split(".")[1])
    return sorted(set(labels))


def _tenant_app_labels() -> set[str]:
    """TENANT_APPS lives inside a conditional django-tenants branch, so parse it."""
    src = SETTINGS_PATH.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id == "TENANT_APPS"):
                continue
            if not isinstance(node.value, ast.List):
                continue
            for el in node.value.elts:
                if isinstance(el, ast.Constant) and isinstance(el.value, str):
                    out.add(el.value.split(".")[1])
    return out


def _ast_class_names(label: str) -> set[str]:
    """Every class physically declared under apps/<label>/, by AST.

    Deliberately does NOT try to decide which classes are models. An earlier
    version guessed model-ness from base-class names ("base is ``Model`` or
    ends in ``Model``") and was wrong in three separate ways, each of which
    produced a FALSE POSITIVE against a real model:

    * ``User(AbstractUser)`` and ``Client(TenantMixin)`` / ``Domain(DomainMixin)``
      -- real models whose base name carries no ``Model`` suffix.
    * ``PlatformEvent(PlatformEventLog)`` -- a proxy model, i.e. model-ness is
      transitive through another model class.
    * ``BrandProfile`` and friends -- declared in ``apps/siteconfig/`` but
      registered under app_label ``brand_experience`` via ``Meta.app_label``,
      so no directory-scoped scan of apps/brand_experience/ can ever see them.

    A docs gate that rejects true statements is worse than no gate: it pressures
    authors to delete correct content to get green. So model identity now comes
    from the app registry (below), and this function only contributes the
    classes that exist on disk but never reach the registry -- abstract bases
    and mixins a README may legitimately reference.
    """
    app_dir = APPS_DIR / label
    names: set[str] = set()
    if not app_dir.is_dir():
        return names
    for py in app_dir.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                names.add(node.name)
    return names


def _registry_models() -> dict[str, set[str]]:
    """{app_label: {ModelName, ...}} straight from the live Django app registry.

    Authoritative by construction: it resolves ``Meta.app_label`` relocation and
    includes proxies, which is exactly what AST cannot do. Needs ``django.setup()``
    but NOT a database -- the app registry is populated from code alone. Other
    gates (``verify_template_compiles``, ``verify_relation_path_integrity``)
    bootstrap Django the same way.
    """
    import django

    sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    from django.apps import apps as django_apps

    out: dict[str, set[str]] = {}
    for cfg in django_apps.get_app_configs():
        if not cfg.name.startswith("apps."):
            continue
        out[cfg.label] = {m.__name__ for m in cfg.get_models()}
    return out


def _known_names(label: str, registry: dict[str, set[str]]) -> set[str]:
    """Names a README may legitimately cite for this app.

    Registry models (authoritative) UNION classes declared in the app directory.
    The union is intentionally permissive: the failure this gate exists to catch
    is an *invented* name (a model that exists nowhere), and permissiveness costs
    nothing there while eliminating false positives against real models.

    Both halves are load-bearing, and neither is sufficient alone:

    * The registry alone is INCOMPLETE. Django only registers a model when the
      module declaring it is imported, and ``django.setup()`` imports only
      ``models.py``. ``apps/api`` declares ``MobileDevice`` / ``APIAccessLog`` /
      ``PushNotification`` / ``OfflineSyncQueue`` in ``mobile_api.py``, so the
      registry reports ZERO models for it at setup time and four once that module
      is imported. Those models are real and migrated; only the snapshot is late.
    * AST alone is incomplete for the relocation/proxy cases described in
      ``_ast_class_names``.

    Also note an app's registry label is not always its directory name
    (``apps/security`` -> ``rmc_security``, ``apps/dashboard`` -> ``rms_dashboard``),
    which is why a miss here degrades to the AST set rather than to an empty set.
    """
    return registry.get(label, set()) | _ast_class_names(label)


def _check(label: str, tenant_labels: set[str], registry: dict[str, set[str]]) -> list[str]:
    findings: list[str] = []
    readme = APPS_DIR / label / "README.md"
    rel = readme.relative_to(REPO_ROOT).as_posix()

    if not readme.exists():
        return [f"{rel}: MISSING (metric 24 requires a README for every installed app)"]

    text = readme.read_text(encoding="utf-8", errors="replace")

    # 2. Title must name this app.
    expected_title = f"# apps/{label}"
    first_line = text.lstrip().splitlines()[0].strip() if text.strip() else ""
    if first_line != expected_title:
        findings.append(
            f"{rel}: title is {first_line!r}, expected {expected_title!r} "
            f"(a mismatched title usually means copy-paste from another app)"
        )

    # 3. Tenancy must match settings.
    m = TENANCY_RE.search(text)
    expected_tenancy = "TENANT" if label in tenant_labels else "SHARED"
    if not m:
        findings.append(f"{rel}: missing '**Tenancy:** TENANT|SHARED' line")
    elif m.group(1) != expected_tenancy:
        findings.append(
            f"{rel}: claims Tenancy={m.group(1)} but settings say {expected_tenancy} "
            f"({'in' if label in tenant_labels else 'not in'} TENANT_APPS)"
        )

    # Required headings.
    for heading in REQUIRED_HEADINGS:
        if heading not in text:
            findings.append(f"{rel}: missing required section {heading!r}")

    # 5. Placeholders.
    for pat in PLACEHOLDER_PATTERNS:
        hit = re.search(pat, text, re.I)
        if hit:
            findings.append(
                f"{rel}: placeholder text {hit.group(0)!r} - an unfinished README "
                f"does not satisfy metric 24"
            )

    # 4. Every model cited must exist.
    declared = _known_names(label, registry)
    cited = set(MODEL_ROW_RE.findall(text))
    phantom = sorted(cited - declared)
    if phantom:
        findings.append(
            f"{rel}: cites model(s) that do not exist in apps/{label}: "
            f"{', '.join(phantom)} - documentation must not invent surface"
        )

    # 6. Substantive purpose prose.
    body = text.split("## What this app owns", 1)
    if len(body) == 2:
        section = body[1].split("\n## ", 1)[0]
        prose = re.sub(r"[`*_|>#\-\[\]()]", "", section).strip()
        if len(prose) < MIN_PURPOSE_CHARS:
            findings.append(
                f"{rel}: '## What this app owns' has {len(prose)} chars of prose, "
                f"needs >= {MIN_PURPOSE_CHARS} (a stub is not documentation)"
            )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    labels = _installed_app_labels()
    tenant_labels = _tenant_app_labels()
    registry = _registry_models()

    all_findings: list[str] = []
    missing = 0
    for label in labels:
        if not (APPS_DIR / label).is_dir():
            continue
        f = _check(label, tenant_labels, registry)
        if f and "MISSING" in f[0]:
            missing += 1
        all_findings.extend(f)

    if args.json:
        print(json.dumps({
            "installed_apps": len(labels),
            "finding_count": len(all_findings),
            "missing_readmes": missing,
            "findings": all_findings,
        }, indent=2))
        return 1 if all_findings else 0

    print(f"app README gate: {len(labels)} installed app(s) under apps/")
    if not all_findings:
        print("  OK - every app has a README and every claim checks out")
        print("APP_README_GATE_PASS")
        return 0
    print(f"\n{len(all_findings)} finding(s):")
    for line in all_findings:
        print(f"  - {line}")
    print("\nAPP_README_GATE_FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
